"""Checkpoint-aware orchestration for the AprilTag/direct-drive mode."""

from .control_modes import create_relocator, relocate_reposition_plan
from .executor import execute_drawing_window
from .models import DrawingError, PlanCheckpoint
from .planner import build_drawing_plan


def _checkpoint(document):
    if not isinstance(document, dict):
        raise DrawingError("invalid_resume_checkpoint")
    try:
        return PlanCheckpoint(
            document["group_index"],
            document["stroke_index"],
            document["next_point_index"],
        )
    except (KeyError, TypeError):
        raise DrawingError("invalid_resume_checkpoint")


def execute_localized_drawing(
    arm,
    chassis,
    localization,
    job,
    drawing_config,
    control_config,
    execution_admission,
    relocation_admission,
    task_id,
    event_sink=None,
    sleep_func=None,
    clock=None,
    max_windows=100,
):
    """Execute windows and relocate without retrying or silently changing mode."""
    if control_config.selected_mode != "localized_baseline":
        raise DrawingError("localized_baseline_mode_required")
    if not isinstance(task_id, str) or not task_id.strip():
        raise DrawingError("localized_task_id_required")
    if isinstance(max_windows, bool) or not isinstance(max_windows, int) or max_windows < 1:
        raise DrawingError("invalid_max_windows")
    emit = event_sink or (lambda _event: None)
    options = {"event": emit}
    if sleep_func is not None:
        options["sleep"] = sleep_func
    if clock is not None:
        options["clock"] = clock
    relocator = create_relocator(
        control_config, chassis, localization, **options
    )

    checkpoint = None
    completed_commands = 0
    relocations = []
    previous_resume = None
    for window_index in range(1, max_windows + 1):
        snapshot = localization.snapshot()
        context = snapshot.get("context") or {}
        generation = snapshot.get("generation")
        if snapshot.get("state") != "locked" or not context:
            raise DrawingError("initial_localization_not_locked")
        if context.get("json_mm_per_rail_mm") != control_config.json_mm_per_rail_mm:
            raise DrawingError("localized_baseline_localization_scale_mismatch")
        offset = context.get("json_axis_offset_mm")
        plan = build_drawing_plan(job, drawing_config, offset, checkpoint)
        window_task = "%s-w%d" % (task_id.strip()[:70], window_index)
        localization.begin_task(window_task, generation)
        emit({
            "event": "localized_window_start",
            "window": window_index,
            "generation": generation,
            "json_axis_offset_mm": offset,
            "checkpoint": None if checkpoint is None else checkpoint.to_dict(),
        })
        try:
            result = execute_drawing_window(
                arm, plan, drawing_config, execution_admission, emit,
                **({} if sleep_func is None else {"sleep_func": sleep_func}),
            )
        except Exception as error:
            try:
                localization.finish_task(
                    window_task, "UNKNOWN", getattr(error, "code", type(error).__name__)
                )
            except Exception:
                pass
            raise
        localization.finish_task(window_task, "DONE", "window_complete")
        completed_commands += result["completed_commands"]
        emit({
            "event": "localized_window_done",
            "window": window_index,
            "complete": plan.complete,
            "completed_commands": result["completed_commands"],
        })
        if plan.complete:
            return {
                "mode": "localized_baseline",
                "windows": window_index,
                "relocations": relocations,
                "completed_commands": completed_commands,
                "final_generation": generation,
                "final_json_axis_offset_mm": offset,
            }

        resume = relocate_reposition_plan(plan, relocator, relocation_admission)
        current_resume = (
            tuple(sorted(resume["checkpoint"].items())),
            resume["json_axis_offset_mm"],
        )
        if current_resume == previous_resume:
            raise DrawingError("localized_baseline_no_checkpoint_progress")
        previous_resume = current_resume
        checkpoint = _checkpoint(resume["checkpoint"])
        relocations.append(resume["relocation"])
        emit({
            "event": "localized_relocation_done",
            "window": window_index,
            **resume["relocation"],
        })
    raise DrawingError("localized_baseline_window_limit")
