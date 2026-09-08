"""Pure conversion of a validated drawing job into abstract PC task steps."""

import math

from .models import DrawingError, DrawingPlan, PlanCheckpoint, PlanStep


def _finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DrawingError("%s must be a finite number" % label)
    value = float(value)
    if not math.isfinite(value):
        raise DrawingError("%s must be a finite number" % label)
    return value


def _clean(value):
    value = round(value, 9)
    return 0.0 if value == 0 else value


def _point_mm(job, geometry, point, json_axis_offset_mm):
    u, v = point
    user_y = (
        u / job.canvas.width * geometry.canvas_width_mm
        + geometry.user_y_offset_mm
        + json_axis_offset_mm
    )
    user_z = (
        (1.0 - v / job.canvas.height) * geometry.canvas_height_mm
        + geometry.user_z_offset_mm
    )
    absolute_user_y = geometry.home_pose_user_y_mm + user_y
    for value in (user_y, user_z, absolute_user_y):
        if not math.isfinite(value):
            raise DrawingError("derived drawing coordinate is not finite")
    return _clean(user_y), _clean(user_z), _clean(absolute_user_y)


def _checkpoint(job, value):
    if value is None:
        return PlanCheckpoint(0, 0, 0)
    if not isinstance(value, PlanCheckpoint):
        raise DrawingError("checkpoint must be PlanCheckpoint")
    if not 0 <= value.group_index < len(job.groups):
        raise DrawingError("checkpoint group index is outside the job")
    group = job.groups[value.group_index]
    if not 0 <= value.stroke_index < len(group.strokes):
        raise DrawingError("checkpoint stroke index is outside the group")
    stroke = group.strokes[value.stroke_index]
    if not 0 <= value.next_point_index < len(stroke.points):
        raise DrawingError("checkpoint point index is outside the stroke")
    return value


def _move_payload(geometry, translation, speed_pct, purpose):
    return {
        "translation_mm": list(translation),
        "user": geometry.user,
        "tool": geometry.tool,
        "accel_pct": geometry.accel_pct,
        "speed_pct": speed_pct,
        "purpose": purpose,
    }


def _inside(geometry, absolute_user_y):
    return (
        geometry.reachable_user_y_min_mm
        <= absolute_user_y
        <= geometry.reachable_user_y_max_mm
    )


def _reposition_step(checkpoint, absolute_user_y_values, geometry):
    lowest = min(absolute_user_y_values)
    highest = max(absolute_user_y_values)
    delta_min = geometry.reachable_user_y_min_mm - lowest
    delta_max = geometry.reachable_user_y_max_mm - highest
    if delta_min > delta_max:
        raise DrawingError("drawing segment is wider than the configured User-Y range")
    delta_min = _clean(delta_min)
    delta_max = _clean(delta_max)
    suggested_delta = _clean((delta_min + delta_max) / 2.0)
    return PlanStep(
        "reposition.required",
        "reposition before checkpoint",
        {
            "checkpoint": checkpoint.to_dict(),
            "target_user_y_mm": list(absolute_user_y_values),
            "reachable_user_y_mm": [
                geometry.reachable_user_y_min_mm,
                geometry.reachable_user_y_max_mm,
            ],
            "required_json_axis_offset_delta_range_mm": [delta_min, delta_max],
            "suggested_json_axis_offset_delta_mm": suggested_delta,
            "requires_pen_up": True,
            "requires_arm_safe": True,
            "requires_new_localization_generation": True,
        },
    )


def build_drawing_plan(job, config, json_axis_offset_mm=0.0, checkpoint=None):
    """Plan until completion or the first pre-motion reachable-range barrier."""
    json_axis_offset_mm = _finite(json_axis_offset_mm, "json_axis_offset_mm")
    start = _checkpoint(job, checkpoint)
    geometry = config.geometry
    pen_slots = {
        group.name: config.pen_slot(group.name)
        for group in job.groups
        if group.strokes
    }
    all_points = [
        point
        for group in job.groups
        for stroke in group.strokes
        for point in stroke.points
    ]
    converted = [
        _point_mm(job, geometry, point, json_axis_offset_mm)
        for point in all_points
    ]
    job_bounds = {
        "normalized_x": [
            min(point[0] for point in all_points),
            max(point[0] for point in all_points),
        ],
        "normalized_y": [
            min(point[1] for point in all_points),
            max(point[1] for point in all_points),
        ],
        "relative_user_y_mm": [
            min(point[0] for point in converted),
            max(point[0] for point in converted),
        ],
        "relative_user_z_mm": [
            min(point[1] for point in converted),
            max(point[1] for point in converted),
        ],
        "absolute_user_y_mm": [
            min(point[2] for point in converted),
            max(point[2] for point in converted),
        ],
    }
    steps = []
    planned_strokes = 0
    planned_points = 0
    arm_commands = 0
    pen_changes = 0

    def add(kind, label, payload):
        nonlocal arm_commands, pen_changes
        steps.append(PlanStep(kind, label, payload))
        if kind in ("arm.home", "arm.relative"):
            arm_commands += 1
        elif kind == "pen.select":
            pen_changes += 1

    for group_index in range(start.group_index, len(job.groups)):
        group = job.groups[group_index]
        stroke_start = start.stroke_index if group_index == start.group_index else 0
        if stroke_start >= len(group.strokes):
            continue
        slot = pen_slots[group.name]
        pen_selected = False
        for stroke_index in range(stroke_start, len(group.strokes)):
            stroke = group.strokes[stroke_index]
            resume_index = (
                start.next_point_index
                if group_index == start.group_index and stroke_index == start.stroke_index
                else 0
            )
            anchor_index = max(0, resume_index - 1)
            anchor_y, anchor_z, anchor_absolute_y = _point_mm(
                job, geometry, stroke.points[anchor_index], json_axis_offset_mm
            )
            if not _inside(geometry, anchor_absolute_y):
                blocked = PlanCheckpoint(group_index, stroke_index, resume_index)
                steps.append(
                    _reposition_step(blocked, (anchor_absolute_y,), geometry)
                )
                return DrawingPlan(
                    job.canonical_sha256,
                    config.canonical_sha256,
                    json_axis_offset_mm,
                    tuple(steps),
                    False,
                    blocked,
                    {
                        "planned_groups": group_index - start.group_index,
                        "planned_strokes": planned_strokes,
                        "planned_points": planned_points,
                        "arm_commands": arm_commands,
                        "pen_changes": pen_changes,
                        "barriers": 1,
                        "job_bounds": job_bounds,
                    },
                )

            if not pen_selected:
                add(
                    "pen.select",
                    "select pen for %s" % group.name,
                    {"group": group.name, "slot": slot},
                )
                pen_selected = True
            prefix = "%s/%s" % (group.name, stroke.id)
            add(
                "arm.home",
                "%s: home" % prefix,
                {
                    "joint_deg": list(geometry.home_joints_deg),
                    "accel_pct": geometry.accel_pct,
                    "speed_pct": geometry.travel_speed_pct,
                    "purpose": "stroke_start",
                },
            )
            add("sleep", "%s: home pause" % prefix, {"seconds": 0.2})
            add(
                "arm.relative",
                "%s: anchor point %d" % (prefix, anchor_index),
                _move_payload(
                    geometry,
                    (0.0, anchor_y, anchor_z),
                    geometry.travel_speed_pct,
                    "stroke_anchor",
                ),
            )
            add(
                "arm.relative",
                "%s: pen down" % prefix,
                _move_payload(
                    geometry,
                    (-geometry.pen_travel_x_mm, 0.0, 0.0),
                    geometry.travel_speed_pct,
                    "pen_down",
                ),
            )
            planned_points += 1
            previous_y, previous_z = anchor_y, anchor_z
            previous_absolute_y = anchor_absolute_y
            for point_index in range(anchor_index + 1, len(stroke.points)):
                if point_index < resume_index:
                    continue
                point_y, point_z, absolute_y = _point_mm(
                    job, geometry, stroke.points[point_index], json_axis_offset_mm
                )
                if not _inside(geometry, absolute_y):
                    add(
                        "arm.relative",
                        "%s: pen up for reposition" % prefix,
                        _move_payload(
                            geometry,
                            (geometry.pen_travel_x_mm, 0.0, 0.0),
                            geometry.travel_speed_pct,
                            "pen_up",
                        ),
                    )
                    add(
                        "arm.home",
                        "%s: safe home for reposition" % prefix,
                        {
                            "joint_deg": list(geometry.home_joints_deg),
                            "accel_pct": geometry.accel_pct,
                            "speed_pct": geometry.travel_speed_pct,
                            "purpose": "reposition_safe_pose",
                        },
                    )
                    blocked = PlanCheckpoint(group_index, stroke_index, point_index)
                    steps.append(
                        _reposition_step(
                            blocked,
                            (previous_absolute_y, absolute_y),
                            geometry,
                        )
                    )
                    return DrawingPlan(
                        job.canonical_sha256,
                        config.canonical_sha256,
                        json_axis_offset_mm,
                        tuple(steps),
                        False,
                        blocked,
                        {
                            "planned_groups": group_index - start.group_index,
                            "planned_strokes": planned_strokes,
                            "planned_points": planned_points,
                            "arm_commands": arm_commands,
                            "pen_changes": pen_changes,
                            "barriers": 1,
                            "job_bounds": job_bounds,
                        },
                    )
                add(
                    "arm.relative",
                    "%s: point %d" % (prefix, point_index),
                    _move_payload(
                        geometry,
                        (
                            0.0,
                            _clean(point_y - previous_y),
                            _clean(point_z - previous_z),
                        ),
                        geometry.draw_speed_pct,
                        "draw_segment",
                    ),
                )
                planned_points += 1
                previous_y, previous_z = point_y, point_z
                previous_absolute_y = absolute_y
            add(
                "arm.relative",
                "%s: pen up" % prefix,
                _move_payload(
                    geometry,
                    (geometry.pen_travel_x_mm, 0.0, 0.0),
                    geometry.travel_speed_pct,
                    "pen_up",
                ),
            )
            add("sleep", "%s: end pause" % prefix, {"seconds": 0.3})
            planned_strokes += 1
        add(
            "pen.return",
            "return pen for %s" % group.name,
            {"group": group.name, "slot": slot},
        )

    return DrawingPlan(
        job.canonical_sha256,
        config.canonical_sha256,
        json_axis_offset_mm,
        tuple(steps),
        True,
        None,
        {
            "planned_groups": len(job.groups) - start.group_index,
            "planned_strokes": planned_strokes,
            "planned_points": planned_points,
            "arm_commands": arm_commands,
            "pen_changes": pen_changes,
            "barriers": 0,
            "job_bounds": job_bounds,
        },
    )
