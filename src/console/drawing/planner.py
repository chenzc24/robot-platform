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
    u_ratio = u / job.canvas.width
    v_ratio = v / job.canvas.height
    target = tuple(
        geometry.canvas_top_left_from_home_mm[index]
        + u_ratio * geometry.canvas_u_vector_from_home_mm[index]
        + v_ratio * geometry.canvas_v_vector_from_home_mm[index]
        + json_axis_offset_mm
        * geometry.rail_offset_vector_from_home_mm_per_json_mm[index]
        for index in range(3)
    )
    for value in target:
        if not math.isfinite(value):
            raise DrawingError("derived drawing coordinate is not finite")
    return tuple(_clean(value) for value in target)


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


def _motion_options(accel_pct=None, speed_pct=None, blend_pct=None):
    options = {}
    if accel_pct is not None:
        options["accel_pct"] = accel_pct
    if speed_pct is not None:
        options["speed_pct"] = speed_pct
    if blend_pct is not None:
        options["blend_pct"] = blend_pct
    return options


def _joint_payload(geometry, joints):
    return {
        "joint_deg": list(joints),
        **_motion_options(geometry.accel_pct, geometry.travel_speed_pct),
    }


def _move_payload(geometry, translation, speed_pct, purpose, blend_pct=None):
    return {
        "translation_mm": list(translation),
        "user": geometry.user,
        "tool": geometry.tool,
        **_motion_options(geometry.accel_pct, speed_pct, blend_pct),
        "purpose": purpose,
    }


def _pen_select_payload(group_name, slot, config):
    rack = config.pen_rack
    depth = rack.change_depth_mm
    geometry = config.geometry
    return {
        "group": group_name,
        "slot": slot.name,
        "purpose": "pick_pen",
        "depth_mm": depth,
        "steps": [
            {
                "kind": "arm.move_joint",
                **_joint_payload(geometry, slot.joint_deg),
            },
            {"kind": "arm.gripper", "width_mm": rack.gripper_open_mm},
            {
                "kind": "arm.relative",
                **_move_payload(
                    geometry,
                    (0.0, 0.0, -depth),
                    geometry.travel_speed_pct,
                    "pen_rack_descend",
                ),
            },
            {"kind": "arm.gripper", "width_mm": rack.gripper_closed_mm},
            {
                "kind": "arm.relative",
                **_move_payload(
                    geometry,
                    (0.0, 0.0, depth),
                    geometry.travel_speed_pct,
                    "pen_rack_ascend",
                ),
            },
        ],
    }


def _pen_return_payload(group_name, slot, config, final_return):
    rack = config.pen_rack
    geometry = config.geometry
    depth = (
        rack.final_return_depth_mm if final_return else rack.change_depth_mm
    )
    steps = [
        {
            "kind": "arm.move_joint",
            **_joint_payload(geometry, slot.joint_deg),
        },
        {
            "kind": "arm.relative",
            **_move_payload(
                geometry,
                (0.0, 0.0, -depth),
                geometry.travel_speed_pct,
                "pen_rack_descend",
            ),
        },
        {"kind": "arm.gripper", "width_mm": rack.gripper_open_mm},
        {
            "kind": "arm.relative",
            **_move_payload(
                geometry,
                (0.0, 0.0, depth),
                geometry.travel_speed_pct,
                "pen_rack_ascend",
            ),
        },
    ]
    if final_return:
        steps.append(
            {
                "kind": "arm.move_joint",
                **_joint_payload(geometry, geometry.home_joints_deg),
            }
        )
    return {
        "group": group_name,
        "slot": slot.name,
        "purpose": "final_return" if final_return else "group_change_return",
        "depth_mm": depth,
        "steps": steps,
    }


def _inside(geometry, home_relative_y):
    return (
        geometry.reachable_home_relative_y_min_mm
        <= home_relative_y
        <= geometry.reachable_home_relative_y_max_mm
    )


def _stroke_payload(geometry, anchor_translation, segments):
    """One lifted-to-lifted controller-side stroke transaction."""
    return {
        "anchor_translation_mm": list(anchor_translation),
        "pen_down_translation_mm": list(geometry.pen_down_delta_from_lift_mm),
        "pen_up_translation_mm": [
            _clean(-value) for value in geometry.pen_down_delta_from_lift_mm
        ],
        "segments_mm": [list(segment) for segment in segments],
        "user": geometry.user,
        "tool": geometry.tool,
        "accel_pct": geometry.accel_pct,
        "travel_speed_pct": geometry.travel_speed_pct,
        "draw_speed_pct": geometry.draw_speed_pct,
        "draw_blend_pct": geometry.draw_blend_pct,
        "purpose": "queued_stroke",
    }


def _reposition_step(checkpoint, absolute_user_y_values, geometry):
    lowest = min(absolute_user_y_values)
    highest = max(absolute_user_y_values)
    delta_min = geometry.reachable_home_relative_y_min_mm - lowest
    delta_max = geometry.reachable_home_relative_y_max_mm - highest
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
            "reachable_home_relative_y_mm": [
                geometry.reachable_home_relative_y_min_mm,
                geometry.reachable_home_relative_y_max_mm,
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
            min(point[1] for point in converted),
            max(point[1] for point in converted),
        ],
        "relative_user_z_mm": [
            min(point[2] for point in converted),
            max(point[2] for point in converted),
        ],
        "absolute_user_y_mm": [
            min(point[1] for point in converted),
            max(point[1] for point in converted),
        ],
        "home_relative_user_x_mm": [
            min(point[0] for point in converted),
            max(point[0] for point in converted),
        ],
    }
    steps = []
    planned_strokes = 0
    planned_points = 0
    arm_commands = 0
    pen_changes = 0
    active_slot = None
    active_group_name = None
    current_lift_position = None

    def add(kind, label, payload):
        nonlocal arm_commands, pen_changes
        steps.append(PlanStep(kind, label, payload))
        if kind in ("arm.home", "arm.relative", "arm.stroke"):
            arm_commands += 1
        elif kind == "pen.select":
            pen_changes += 1

    def prepare_reposition(prefix):
        """Leave no pen held so checkpoint replanning remains stateless."""
        nonlocal active_slot, active_group_name, current_lift_position
        if active_slot is not None:
            add(
                "arm.home",
                "%s: home before pen return" % prefix,
                {
                    **_joint_payload(geometry, geometry.home_joints_deg),
                    "purpose": "reposition_pen_return_prepare",
                },
            )
            add(
                "pen.return",
                "%s: return pen for reposition" % prefix,
                _pen_return_payload(
                    active_group_name,
                    active_slot,
                    config,
                    final_return=False,
                ),
            )
            active_slot = None
            active_group_name = None
        add(
            "arm.home",
            "%s: safe home for reposition" % prefix,
            {
                **_joint_payload(geometry, geometry.home_joints_deg),
                "purpose": "reposition_safe_pose",
            },
        )
        current_lift_position = None

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
            anchor = _point_mm(
                job, geometry, stroke.points[anchor_index], json_axis_offset_mm
            )
            if not _inside(geometry, anchor[1]):
                blocked = PlanCheckpoint(group_index, stroke_index, resume_index)
                prepare_reposition("%s/%s" % (group.name, stroke.id))
                steps.append(
                    _reposition_step(blocked, (anchor[1],), geometry)
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
                if active_slot is None:
                    add(
                        "pen.select",
                        "select pen for %s" % group.name,
                        _pen_select_payload(group.name, slot, config),
                    )
                    active_slot = slot
                    active_group_name = group.name
                    current_lift_position = None
                elif active_slot.name != slot.name:
                    add(
                        "pen.return",
                        "return pen before %s" % group.name,
                        _pen_return_payload(
                            active_group_name,
                            active_slot,
                            config,
                            final_return=False,
                        ),
                    )
                    add(
                        "pen.select",
                        "select pen for %s" % group.name,
                        _pen_select_payload(group.name, slot, config),
                    )
                    active_slot = slot
                    active_group_name = group.name
                    current_lift_position = None
                else:
                    active_group_name = group.name
                pen_selected = True
            prefix = "%s/%s" % (group.name, stroke.id)
            if current_lift_position is None:
                add(
                    "arm.home",
                    "%s: Home reference" % prefix,
                    {
                        **_joint_payload(geometry, geometry.home_joints_deg),
                        "purpose": "stroke_reference_home",
                    },
                )
                anchor_translation = anchor
            else:
                anchor_translation = tuple(
                    _clean(anchor[index] - current_lift_position[index])
                    for index in range(3)
                )
            segments = []
            previous = anchor
            planned_points += 1
            blocked = None
            for point_index in range(anchor_index + 1, len(stroke.points)):
                if point_index < resume_index:
                    continue
                point = _point_mm(
                    job, geometry, stroke.points[point_index], json_axis_offset_mm
                )
                if not _inside(geometry, point[1]):
                    blocked = PlanCheckpoint(group_index, stroke_index, point_index)
                    blocked_point = point
                    break
                segments.append(
                    tuple(
                        _clean(point[index] - previous[index])
                        for index in range(3)
                    )
                )
                planned_points += 1
                previous = point
            if not segments:
                if blocked is None:
                    raise DrawingError("stroke_has_no_draw_segments")
                prepare_reposition(prefix)
                steps.append(
                    _reposition_step(
                        blocked,
                        (anchor[1], blocked_point[1]),
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
                "arm.stroke",
                "%s: queued points %d-%d" % (prefix, anchor_index, anchor_index + len(segments)),
                _stroke_payload(geometry, anchor_translation, segments),
            )
            current_lift_position = previous
            if blocked is not None:
                prepare_reposition(prefix)
                steps.append(
                    _reposition_step(
                        blocked,
                        (previous[1], blocked_point[1]),
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
            planned_strokes += 1
    if active_slot is not None:
        add(
            "pen.return",
            "final pen return for %s" % active_group_name,
            _pen_return_payload(
                active_group_name,
                active_slot,
                config,
                final_return=True,
            ),
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
