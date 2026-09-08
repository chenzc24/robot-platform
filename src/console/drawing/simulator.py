"""No-device rehearsal of Localized Baseline against a one-axis physical model."""

import math
from dataclasses import replace

from .loader import canonical_document
from .models import DrawingError
from .planner import build_drawing_plan


def _finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DrawingError("%s must be a finite number" % label)
    value = float(value)
    if not math.isfinite(value):
        raise DrawingError("%s must be a finite number" % label)
    return value


def _clean(value):
    value = round(float(value), 9)
    return 0.0 if value == 0 else value


def _checkpoint_dict(checkpoint):
    return None if checkpoint is None else checkpoint.to_dict()


def _point_rank(job, checkpoint):
    if checkpoint is None:
        return 0
    rank = 0
    for group_index, group in enumerate(job.groups):
        for stroke_index, stroke in enumerate(group.strokes):
            if (
                group_index == checkpoint.group_index
                and stroke_index == checkpoint.stroke_index
            ):
                return rank + checkpoint.next_point_index
            rank += len(stroke.points)
    raise DrawingError("simulation checkpoint is outside the drawing")


def _simulation_config(config, reachable_min_mm, reachable_max_mm):
    geometry = config.geometry
    low = (
        geometry.reachable_user_y_min_mm
        if reachable_min_mm is None
        else _finite(reachable_min_mm, "reachable_min_mm")
    )
    high = (
        geometry.reachable_user_y_max_mm
        if reachable_max_mm is None
        else _finite(reachable_max_mm, "reachable_max_mm")
    )
    if low >= high:
        raise DrawingError("simulated reachable User-Y minimum must be below maximum")
    return replace(
        config,
        geometry=replace(
            geometry,
            reachable_user_y_min_mm=low,
            reachable_user_y_max_mm=high,
        ),
    )


def _safety_sequence(plan):
    result = []
    if any(
        step.kind == "arm.relative" and step.payload.get("purpose") == "pen_up"
        for step in plan.steps[:-1]
    ):
        result.append("pen_up")
    if any(
        step.kind == "pen.return" and "for reposition" in step.label
        for step in plan.steps[:-1]
    ):
        result.append("pen_return")
    if not any(
        step.kind == "arm.home"
        and step.payload.get("purpose") == "reposition_safe_pose"
        for step in plan.steps[:-1]
    ):
        raise DrawingError("simulation barrier has no safe-home step")
    result.append("arm_home_safe")
    return result


def _result(
    job,
    source_config,
    simulation_config,
    windows,
    generation,
    true_reference_mm,
    measured_reference_mm,
    initial_true_mm,
    initial_measured_mm,
    true_rail_mm,
    measured_rail_mm,
    offset_mm,
    scale,
    motion_gain,
    stop_overshoot_mm,
    localization_errors_mm,
    rail_min_mm,
    rail_max_mm,
):
    geometry = simulation_config.geometry
    relocations = [
        window["relocation"] for window in windows
        if window["relocation"] is not None
    ]
    commanded_moves = [
        relocation["commanded_open_loop_rail_move_mm"]
        for relocation in relocations
    ]
    actual_moves = [
        relocation["actual_true_rail_move_mm"] for relocation in relocations
    ]
    directions = [1 if value > 0 else -1 for value in actual_moves if value]
    direction_changes = sum(
        directions[index] != directions[index - 1]
        for index in range(1, len(directions))
    )
    warnings = []
    if direction_changes:
        warnings.append("simulated_rail_direction_reversal")
    if motion_gain != 1 or stop_overshoot_mm != 0:
        warnings.append("open_loop_motion_error_enabled")
    if any(
        value != localization_errors_mm[0]
        for value in localization_errors_mm[1:]
    ):
        warnings.append("varying_localization_error_enabled")
    return {
        "schema": "localized-baseline-rehearsal/2",
        "simulation_only": True,
        "mode": "localized_baseline",
        "assumptions": [
            "one_dimensional_translation_only",
            "fixed_motion_gain_and_stop_overshoot",
            "predetermined_apriltag_measurement_errors",
            "no_yaw_or_lateral_motion",
            "no_tag_dropout_or_latency",
            "enabled_stopped_is_logical_not_measured_physical_stop",
            "no_collision_or_robot_kinematics_model",
        ],
        "calibration": {
            "true_rail_reference_mm": true_reference_mm,
            "measured_rail_reference_mm": measured_reference_mm,
            "initial_true_rail_position_mm": initial_true_mm,
            "initial_measured_rail_position_mm": initial_measured_mm,
            "json_mm_per_rail_mm": scale,
            "formula": (
                "json_axis_offset_mm = scale * "
                "(measured_rail_mm - measured_reference_mm)"
            ),
        },
        "physical_model": {
            "motion_gain": motion_gain,
            "stop_overshoot_mm": stop_overshoot_mm,
            "localization_errors_mm": list(localization_errors_mm),
            "rail_min_mm": rail_min_mm,
            "rail_max_mm": rail_max_mm,
            "move_formula": (
                "actual_move = commanded_move * motion_gain + "
                "sign(commanded_move) * stop_overshoot_mm"
            ),
        },
        "geometry": {
            "canvas_width_mm": geometry.canvas_width_mm,
            "canvas_height_mm": geometry.canvas_height_mm,
            "user_y_offset_mm": geometry.user_y_offset_mm,
            "user_z_offset_mm": geometry.user_z_offset_mm,
            "home_pose_user_y_mm": geometry.home_pose_user_y_mm,
            "reachable_user_y_min_mm": geometry.reachable_user_y_min_mm,
            "reachable_user_y_max_mm": geometry.reachable_user_y_max_mm,
            "pen_travel_x_mm": geometry.pen_travel_x_mm,
            "user": geometry.user,
            "tool": geometry.tool,
        },
        "drawing": canonical_document(job),
        "job_sha256": job.canonical_sha256,
        "source_config_sha256": source_config.canonical_sha256,
        "source_config_reach_overridden": (
            geometry.reachable_user_y_min_mm
            != source_config.geometry.reachable_user_y_min_mm
            or geometry.reachable_user_y_max_mm
            != source_config.geometry.reachable_user_y_max_mm
        ),
        "windows": windows,
        "summary": {
            "outcome": "complete",
            "groups": len(job.groups),
            "strokes": job.stroke_count,
            "points": job.point_count,
            "windows": len(windows),
            "relocations": len(relocations),
            "final_generation": generation,
            "final_true_rail_position_mm": true_rail_mm,
            "final_measured_rail_position_mm": measured_rail_mm,
            "final_json_axis_offset_mm": offset_mm,
            "total_absolute_commanded_rail_travel_mm": _clean(
                sum(abs(value) for value in commanded_moves)
            ),
            "total_absolute_rail_travel_mm": _clean(
                sum(abs(value) for value in actual_moves)
            ),
            "rail_direction_changes": direction_changes,
            "scenario_warnings": warnings,
        },
    }


def simulate_localized_baseline(
    job,
    config,
    rail_reference_mm=0.0,
    initial_rail_position_mm=None,
    json_mm_per_rail_mm=-1.0,
    reachable_min_mm=None,
    reachable_max_mm=None,
    motion_gain=1.0,
    stop_overshoot_mm=0.0,
    localization_errors_mm=(0.0,),
    rail_min_mm=None,
    rail_max_mm=None,
    max_windows=100,
):
    """Rehearse planner commands against an independent physical model."""
    true_reference_mm = _finite(rail_reference_mm, "rail_reference_mm")
    if initial_rail_position_mm is None:
        initial_rail_position_mm = true_reference_mm
    initial_true_mm = _finite(
        initial_rail_position_mm, "initial_rail_position_mm"
    )
    scale = _finite(json_mm_per_rail_mm, "json_mm_per_rail_mm")
    if scale == 0:
        raise DrawingError("json_mm_per_rail_mm must not be zero")
    if isinstance(max_windows, bool) or not isinstance(max_windows, int) or max_windows < 1:
        raise DrawingError("max_windows must be a positive integer")
    motion_gain = _finite(motion_gain, "motion_gain")
    stop_overshoot_mm = _finite(stop_overshoot_mm, "stop_overshoot_mm")
    if motion_gain < 0:
        raise DrawingError("motion_gain must not be negative")
    if stop_overshoot_mm < 0:
        raise DrawingError("stop_overshoot_mm must not be negative")
    if not isinstance(localization_errors_mm, (tuple, list)) or not localization_errors_mm:
        raise DrawingError("localization_errors_mm must contain at least one value")
    localization_errors_mm = tuple(
        _finite(value, "localization_errors_mm")
        for value in localization_errors_mm
    )
    rail_min_mm = None if rail_min_mm is None else _finite(rail_min_mm, "rail_min_mm")
    rail_max_mm = None if rail_max_mm is None else _finite(rail_max_mm, "rail_max_mm")
    if (rail_min_mm is None) != (rail_max_mm is None):
        raise DrawingError("rail_min_mm and rail_max_mm must be supplied together")
    if rail_min_mm is not None and rail_min_mm >= rail_max_mm:
        raise DrawingError("rail minimum must be below maximum")
    if rail_min_mm is not None and not rail_min_mm <= initial_true_mm <= rail_max_mm:
        raise DrawingError("initial true rail position is outside physical bounds")

    def localization_error(lock_index):
        if len(localization_errors_mm) == 1:
            return localization_errors_mm[0]
        if lock_index >= len(localization_errors_mm):
            raise DrawingError("localization error sequence exhausted")
        return localization_errors_mm[lock_index]

    simulation_config = _simulation_config(
        config, reachable_min_mm, reachable_max_mm
    )
    measured_reference_mm = _clean(
        true_reference_mm + localization_error(0)
    )
    true_rail_mm = initial_true_mm
    measured_rail_mm = _clean(true_rail_mm + localization_error(1))
    initial_measured_mm = measured_rail_mm
    offset_mm = _clean(scale * (measured_rail_mm - measured_reference_mm))
    checkpoint = None
    previous_resume = None
    generation = 1
    windows = []

    for window_index in range(1, max_windows + 1):
        start_checkpoint = checkpoint
        plan = build_drawing_plan(
            job,
            simulation_config,
            json_axis_offset_mm=offset_mm,
            checkpoint=checkpoint,
        )
        end_checkpoint = plan.next_checkpoint
        window = {
            "index": window_index,
            "generation": generation,
            "true_rail_position_mm": _clean(true_rail_mm),
            "measured_rail_position_mm": measured_rail_mm,
            "measured_rail_delta_from_reference_mm": _clean(
                measured_rail_mm - measured_reference_mm
            ),
            "localization_error_mm": localization_error(generation),
            "json_axis_offset_mm": offset_mm,
            "checkpoint_start": _checkpoint_dict(start_checkpoint),
            "checkpoint_end": _checkpoint_dict(end_checkpoint),
            "point_rank_start": _point_rank(job, start_checkpoint),
            "point_rank_end_exclusive": (
                job.point_count
                if plan.complete
                else _point_rank(job, end_checkpoint)
            ),
            "complete": plan.complete,
            "statistics": dict(plan.statistics),
            "relocation": None,
        }
        if plan.complete:
            windows.append(window)
            return _result(
                job, config, simulation_config, windows, generation,
                true_reference_mm, measured_reference_mm, initial_true_mm,
                initial_measured_mm, _clean(true_rail_mm), measured_rail_mm,
                offset_mm, scale, motion_gain, stop_overshoot_mm,
                localization_errors_mm, rail_min_mm, rail_max_mm,
            )

        barrier = plan.steps[-1]
        if barrier.kind != "reposition.required":
            raise DrawingError("incomplete simulation plan has no reposition barrier")
        delta_mm = _finite(
            barrier.payload.get("suggested_json_axis_offset_delta_mm"),
            "suggested_json_axis_offset_delta_mm",
        )
        commanded_move_mm = _clean(delta_mm / scale)
        direction = 0 if commanded_move_mm == 0 else (1 if commanded_move_mm > 0 else -1)
        actual_move_mm = _clean(
            commanded_move_mm * motion_gain + direction * stop_overshoot_mm
        )
        next_true_mm = _clean(true_rail_mm + actual_move_mm)
        if rail_min_mm is not None and not rail_min_mm <= next_true_mm <= rail_max_mm:
            raise DrawingError("simulated true rail move exceeds physical bounds")
        next_measured_mm = _clean(
            next_true_mm + localization_error(generation + 1)
        )
        next_offset_mm = _clean(
            scale * (next_measured_mm - measured_reference_mm)
        )
        resume_signature = (
            tuple(sorted(end_checkpoint.to_dict().items())), next_offset_mm
        )
        if resume_signature == previous_resume:
            raise DrawingError("simulation made no checkpoint or offset progress")
        previous_resume = resume_signature
        window["relocation"] = {
            "requested_json_axis_offset_delta_mm": _clean(delta_mm),
            "required_delta_range_mm": list(
                barrier.payload["required_json_axis_offset_delta_range_mm"]
            ),
            "commanded_open_loop_rail_move_mm": commanded_move_mm,
            "actual_true_rail_move_mm": actual_move_mm,
            "true_rail_position_after_mm": next_true_mm,
            "localization_error_after_mm": localization_error(generation + 1),
            "measured_rail_position_after_mm": next_measured_mm,
            "logical_stop_state": "enabled_stopped",
            "generation_after": generation + 1,
            "measured_json_axis_offset_after_mm": next_offset_mm,
            "sequence": _safety_sequence(plan) + [
                "chassis_direct_move", "stop", "enabled_stopped", "settle",
                "apriltag_lock_new_generation", "resume_checkpoint",
            ],
        }
        windows.append(window)
        checkpoint = end_checkpoint
        true_rail_mm = next_true_mm
        measured_rail_mm = next_measured_mm
        offset_mm = next_offset_mm
        generation += 1

    raise DrawingError("simulation window limit reached")
