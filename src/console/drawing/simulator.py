"""Deterministic, no-device rehearsal for the localized Baseline coordinate chain."""

import math
from dataclasses import replace

from .loader import canonical_document
from .models import DrawingError, PlanCheckpoint
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


def simulate_localized_baseline(
    job,
    config,
    rail_reference_mm=0.0,
    initial_rail_position_mm=None,
    json_mm_per_rail_mm=-1.0,
    reachable_min_mm=None,
    reachable_max_mm=None,
    max_windows=100,
):
    """Plan idealized localized windows without importing any device module.

    Every planner barrier is satisfied exactly at its suggested offset. The
    simulated chassis move is followed by logical STOP/enabled_stopped and a
    perfect new localization generation. This is a coordinate rehearsal, not a
    dynamics, vision-noise, collision, or physical-stop model.
    """
    rail_reference_mm = _finite(rail_reference_mm, "rail_reference_mm")
    if initial_rail_position_mm is None:
        initial_rail_position_mm = rail_reference_mm
    rail_position_mm = _finite(initial_rail_position_mm, "initial_rail_position_mm")
    scale = _finite(json_mm_per_rail_mm, "json_mm_per_rail_mm")
    if scale == 0:
        raise DrawingError("json_mm_per_rail_mm must not be zero")
    if isinstance(max_windows, bool) or not isinstance(max_windows, int) or max_windows < 1:
        raise DrawingError("max_windows must be a positive integer")

    simulation_config = _simulation_config(
        config, reachable_min_mm, reachable_max_mm
    )
    geometry = simulation_config.geometry
    offset_mm = _clean(scale * (rail_position_mm - rail_reference_mm))
    checkpoint = None
    previous_resume = None
    generation = 1
    windows = []
    total_points = job.point_count

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
            "rail_position_mm": _clean(rail_position_mm),
            "rail_delta_from_reference_mm": _clean(
                rail_position_mm - rail_reference_mm
            ),
            "json_axis_offset_mm": offset_mm,
            "checkpoint_start": _checkpoint_dict(start_checkpoint),
            "checkpoint_end": _checkpoint_dict(end_checkpoint),
            "point_rank_start": _point_rank(job, start_checkpoint),
            "point_rank_end_exclusive": (
                total_points if plan.complete else _point_rank(job, end_checkpoint)
            ),
            "complete": plan.complete,
            "statistics": dict(plan.statistics),
            "relocation": None,
        }
        if plan.complete:
            windows.append(window)
            rail_moves = [
                item["relocation"]["simulated_direct_rail_move_mm"]
                for item in windows
                if item["relocation"] is not None
            ]
            directions = [1 if value > 0 else -1 for value in rail_moves if value]
            direction_changes = sum(
                directions[index] != directions[index - 1]
                for index in range(1, len(directions))
            )
            scenario_warnings = []
            if direction_changes:
                scenario_warnings.append("simulated_rail_direction_reversal")
            return {
                "schema": "localized-baseline-rehearsal/1",
                "simulation_only": True,
                "mode": "localized_baseline",
                "assumptions": [
                    "perfect_one_dimensional_translation",
                    "perfect_relocalization_at_suggested_offset",
                    "no_yaw_or_lateral_motion",
                    "no_camera_noise_or_tag_dropout",
                    "enabled_stopped_is_logical_not_measured_physical_stop",
                    "no_collision_or_robot_kinematics_model",
                ],
                "calibration": {
                    "rail_reference_mm": rail_reference_mm,
                    "initial_rail_position_mm": _clean(
                        _finite(initial_rail_position_mm, "initial_rail_position_mm")
                    ),
                    "json_mm_per_rail_mm": scale,
                    "formula": "json_axis_offset_mm = scale * (rail_position_mm - rail_reference_mm)",
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
                "source_config_sha256": config.canonical_sha256,
                "source_config_reach_overridden": (
                    geometry.reachable_user_y_min_mm
                    != config.geometry.reachable_user_y_min_mm
                    or geometry.reachable_user_y_max_mm
                    != config.geometry.reachable_user_y_max_mm
                ),
                "windows": windows,
                "summary": {
                    "groups": len(job.groups),
                    "strokes": job.stroke_count,
                    "points": job.point_count,
                    "windows": len(windows),
                    "relocations": len(windows) - 1,
                    "final_generation": generation,
                    "final_rail_position_mm": _clean(rail_position_mm),
                    "final_json_axis_offset_mm": offset_mm,
                    "total_absolute_rail_travel_mm": _clean(
                        sum(abs(value) for value in rail_moves)
                    ),
                    "rail_direction_changes": direction_changes,
                    "scenario_warnings": scenario_warnings,
                },
            }

        barrier = plan.steps[-1]
        if barrier.kind != "reposition.required":
            raise DrawingError("incomplete simulation plan has no reposition barrier")
        delta_mm = _finite(
            barrier.payload.get("suggested_json_axis_offset_delta_mm"),
            "suggested_json_axis_offset_delta_mm",
        )
        next_offset_mm = _clean(offset_mm + delta_mm)
        rail_move_mm = _clean(delta_mm / scale)
        next_rail_position_mm = _clean(rail_position_mm + rail_move_mm)
        measured_offset_mm = _clean(
            scale * (next_rail_position_mm - rail_reference_mm)
        )
        resume_signature = (
            tuple(sorted(end_checkpoint.to_dict().items())),
            measured_offset_mm,
        )
        if resume_signature == previous_resume:
            raise DrawingError("simulation made no checkpoint or offset progress")
        previous_resume = resume_signature
        safety_sequence = []
        if any(
            step.kind == "arm.relative"
            and step.payload.get("purpose") == "pen_up"
            for step in plan.steps[:-1]
        ):
            safety_sequence.append("pen_up")
        if any(
            step.kind == "pen.return" and "for reposition" in step.label
            for step in plan.steps[:-1]
        ):
            safety_sequence.append("pen_return")
        if not any(
            step.kind == "arm.home"
            and step.payload.get("purpose") == "reposition_safe_pose"
            for step in plan.steps[:-1]
        ):
            raise DrawingError("simulation barrier has no safe-home step")
        safety_sequence.append("arm_home_safe")
        window["relocation"] = {
            "requested_json_axis_offset_delta_mm": _clean(delta_mm),
            "required_delta_range_mm": list(
                barrier.payload["required_json_axis_offset_delta_range_mm"]
            ),
            "simulated_direct_rail_move_mm": rail_move_mm,
            "rail_position_after_mm": next_rail_position_mm,
            "logical_stop_state": "enabled_stopped",
            "generation_after": generation + 1,
            "measured_json_axis_offset_after_mm": measured_offset_mm,
            "sequence": safety_sequence + [
                "chassis_direct_move",
                "stop",
                "enabled_stopped",
                "settle",
                "apriltag_lock_new_generation",
                "resume_checkpoint",
            ],
        }
        windows.append(window)
        checkpoint = end_checkpoint
        rail_position_mm = next_rail_position_mm
        offset_mm = measured_offset_mm
        generation += 1

    raise DrawingError("simulation window limit reached")
