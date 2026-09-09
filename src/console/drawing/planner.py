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
    seen = set()
    for item in value.completed_strokes:
        if (
            not isinstance(item, tuple)
            or len(item) != 2
            or type(item[0]) is not int
            or type(item[1]) is not int
        ):
            raise DrawingError("checkpoint completed strokes are invalid")
        group_index, stroke_index = item
        if not 0 <= group_index < len(job.groups):
            raise DrawingError("checkpoint completed group index is outside the job")
        if not 0 <= stroke_index < len(job.groups[group_index].strokes):
            raise DrawingError("checkpoint completed stroke index is outside the group")
        if item in seen:
            raise DrawingError("checkpoint completed strokes contain duplicates")
        seen.add(item)
    if (value.group_index, value.stroke_index) in seen:
        raise DrawingError("checkpoint current stroke is already completed")
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
    """Plan every reachable stroke in one spatial window, then relocate."""
    json_axis_offset_mm = _finite(json_axis_offset_mm, "json_axis_offset_mm")
    start = _checkpoint(job, checkpoint)
    checkpoint_supplied = checkpoint is not None
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
    completed = set(start.completed_strokes)
    touched_groups = set()

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

    def statistics(barriers):
        return {
            "planned_groups": len(touched_groups),
            "planned_strokes": planned_strokes,
            "planned_points": planned_points,
            "arm_commands": arm_commands,
            "pen_changes": pen_changes,
            "barriers": barriers,
            "job_bounds": job_bounds,
        }

    def stroke_state(group_index, stroke_index):
        group = job.groups[group_index]
        stroke = group.strokes[stroke_index]
        key = (group_index, stroke_index)
        resume_index = (
            start.next_point_index
            if checkpoint_supplied
            and key == (start.group_index, start.stroke_index)
            else 0
        )
        anchor_index = max(0, resume_index - 1)
        points = tuple(
            _point_mm(job, geometry, point, json_axis_offset_mm)
            for point in stroke.points[anchor_index:]
        )
        reachable_prefix = 0
        if _inside(geometry, points[0][1]):
            reachable_prefix = 1
            for point in points[1:]:
                if not _inside(geometry, point[1]):
                    break
                reachable_prefix += 1
        return {
            "key": key,
            "group_index": group_index,
            "stroke_index": stroke_index,
            "group": group,
            "stroke": stroke,
            "resume_index": resume_index,
            "anchor_index": anchor_index,
            "points": points,
            "reachable_prefix": reachable_prefix,
            "fully_reachable": reachable_prefix == len(points),
        }

    states = [
        stroke_state(group_index, stroke_index)
        for group_index, group in enumerate(job.groups)
        for stroke_index, _stroke in enumerate(group.strokes)
        if (group_index, stroke_index) not in completed
    ]

    def select_pen(state):
        nonlocal active_slot, active_group_name, current_lift_position
        group = state["group"]
        slot = pen_slots[group.name]
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
                    active_group_name, active_slot, config, final_return=False
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

    def draw_state(state, point_count):
        nonlocal current_lift_position, planned_points, planned_strokes
        select_pen(state)
        group = state["group"]
        stroke = state["stroke"]
        points = state["points"][:point_count]
        prefix = "%s/%s" % (group.name, stroke.id)
        anchor = points[0]
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
        segments = [
            tuple(
                _clean(point[index] - previous[index])
                for index in range(3)
            )
            for previous, point in zip(points, points[1:])
        ]
        if not segments:
            raise DrawingError("stroke_has_no_draw_segments")
        add(
            "arm.stroke",
            "%s: queued points %d-%d"
            % (
                prefix,
                state["anchor_index"],
                state["anchor_index"] + len(segments),
            ),
            _stroke_payload(geometry, anchor_translation, segments),
        )
        current_lift_position = points[-1]
        planned_points += len(points)
        touched_groups.add(state["group_index"])
        if point_count == len(state["points"]):
            completed.add(state["key"])
            planned_strokes += 1

    # Spatial priority: scan all color groups, then execute every whole stroke
    # that fits the current physical window. Group order is retained only inside
    # that window so pen changes remain bounded.
    for state in states:
        if state["fully_reachable"]:
            draw_state(state, len(state["points"]))

    remaining = [state for state in states if state["key"] not in completed]
    partial = next(
        (
            state
            for state in remaining
            if 1 < state["reachable_prefix"] < len(state["points"])
        ),
        None,
    )
    if partial is not None:
        draw_state(partial, partial["reachable_prefix"])
        next_point_index = (
            partial["anchor_index"] + partial["reachable_prefix"]
        )
        blocked = PlanCheckpoint(
            partial["group_index"],
            partial["stroke_index"],
            next_point_index,
            tuple(sorted(completed)),
        )
        prefix = "%s/%s" % (partial["group"].name, partial["stroke"].id)
        previous = partial["points"][partial["reachable_prefix"] - 1]
        blocked_point = partial["points"][partial["reachable_prefix"]]
        prepare_reposition(prefix)
        steps.append(
            _reposition_step(blocked, (previous[1], blocked_point[1]), geometry)
        )
        return DrawingPlan(
            job.canonical_sha256,
            config.canonical_sha256,
            json_axis_offset_mm,
            tuple(steps),
            False,
            blocked,
            statistics(1),
        )

    if remaining:
        width = (
            geometry.reachable_home_relative_y_max_mm
            - geometry.reachable_home_relative_y_min_mm
        )

        def reposition_values(state):
            values = tuple(point[1] for point in state["points"])
            if max(values) - min(values) <= width:
                return values
            if state["reachable_prefix"] == 0:
                return values[:1]
            return values[:2]

        # Sweep toward the lowest remaining drawing coordinate. This makes the
        # window sequence deterministic and prevents color-major ping-pong.
        target = min(
            remaining,
            key=lambda state: (
                min(point[1] for point in state["points"]),
                max(point[1] for point in state["points"]),
                state["group_index"],
                state["stroke_index"],
            ),
        )
        blocked = PlanCheckpoint(
            target["group_index"],
            target["stroke_index"],
            target["resume_index"],
            tuple(sorted(completed)),
        )
        prefix = "%s/%s" % (target["group"].name, target["stroke"].id)
        prepare_reposition(prefix)
        steps.append(
            _reposition_step(blocked, reposition_values(target), geometry)
        )
        return DrawingPlan(
            job.canonical_sha256,
            config.canonical_sha256,
            json_axis_offset_mm,
            tuple(steps),
            False,
            blocked,
            statistics(1),
        )

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
        statistics(0),
    )
