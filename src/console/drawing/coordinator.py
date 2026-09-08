"""Checkpoint-aware orchestration for every explicit drawing mode."""

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


def execute_drawing(
    arm,
    chassis,
    localization,
    job,
    drawing_config,
    control_config,
    execution_admission,
    relocation_admission,
    task_id=None,
    event_sink=None,
    sleep_func=None,
    clock=None,
    max_windows=100,
):
    """Execute windows and relocate without retrying or changing mode."""
    mode = control_config.selected_mode
    uses_localization = mode in ("localized_baseline", "advanced")
    event_prefix = "localized" if mode == "localized_baseline" else mode
    if uses_localization:
        if localization is None:
            raise DrawingError("%s_mode_requires_localization" % mode)
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
    offset = control_config.baseline.initial_json_axis_offset_mm
    completed_commands = 0
    relocations = []
    previous_resume = None
    for window_index in range(1, max_windows + 1):
        generation = None
        if uses_localization:
            snapshot = localization.snapshot()
            context = snapshot.get("context") or {}
            generation = snapshot.get("generation")
            if snapshot.get("state") != "locked" or not context:
                raise DrawingError("initial_localization_not_locked")
            if context.get("json_mm_per_rail_mm") != control_config.json_mm_per_rail_mm:
                raise DrawingError("%s_localization_scale_mismatch" % mode)
            offset = context.get("json_axis_offset_mm")
        plan = build_drawing_plan(job, drawing_config, offset, checkpoint)
        window_task = None
        if uses_localization:
            window_task = "%s-w%d" % (task_id.strip()[:70], window_index)
            localization.begin_task(window_task, generation)
        emit({
            "event": "%s_window_start" % event_prefix,
            "mode": mode,
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
            if uses_localization:
                try:
                    localization.finish_task(
                        window_task, "UNKNOWN", getattr(error, "code", type(error).__name__)
                    )
                except Exception:
                    pass
            raise
        if uses_localization:
            localization.finish_task(window_task, "DONE", "window_complete")
        completed_commands += result["completed_commands"]
        emit({
            "event": "%s_window_done" % event_prefix,
            "mode": mode,
            "window": window_index,
            "complete": plan.complete,
            "completed_commands": result["completed_commands"],
        })
        if plan.complete:
            return {
                "mode": mode,
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
            raise DrawingError("%s_no_checkpoint_progress" % mode)
        previous_resume = current_resume
        checkpoint = _checkpoint(resume["checkpoint"])
        offset = resume["json_axis_offset_mm"]
        relocations.append(resume["relocation"])
        emit({
            "event": "%s_relocation_done" % event_prefix,
            "mode": mode,
            "window": window_index,
            **resume["relocation"],
        })
    raise DrawingError("%s_window_limit" % mode)


def execute_localized_drawing(*args, **kwargs):
    """Compatibility wrapper for the Localized Baseline entry point."""
    control_config = args[5] if len(args) > 5 else kwargs.get("control_config")
    if control_config is None or control_config.selected_mode != "localized_baseline":
        raise DrawingError("localized_baseline_mode_required")
    return execute_drawing(*args, **kwargs)
