"""Strict local configuration for offline drawing geometry and pen mapping."""

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

from .models import DrawingError


_TOP_FIELDS = {
    "production_ready",
    "flat_group_name",
    "group_pen_slots",
    "pen_rack",
    "geometry",
}
_PEN_RACK_FIELDS = {
    "slots",
    "change_depth_mm",
    "final_return_depth_mm",
    "gripper_open_mm",
    "gripper_closed_mm",
}
_PEN_SLOT_NAMES = {"P1", "P2", "P3", "P4"}
_LEGACY_GEOMETRY_FIELDS = {
    "canvas_width_mm",
    "canvas_height_mm",
    "user_y_offset_mm",
    "user_z_offset_mm",
    "home_pose_user_y_mm",
    "reachable_user_y_min_mm",
    "reachable_user_y_max_mm",
    "pen_travel_x_mm",
    "home_joints_deg",
    "user",
    "tool",
    "draw_speed_pct",
    "draw_blend_pct",
    "travel_speed_pct",
    "accel_pct",
}
_HOME_RELATIVE_GEOMETRY_FIELDS = {
    "canvas_width_mm",
    "canvas_height_mm",
    "canvas_top_left_from_home_mm",
    "canvas_u_vector_from_home_mm",
    "canvas_v_vector_from_home_mm",
    "rail_offset_vector_from_home_mm_per_json_mm",
    "reachable_home_relative_y_min_mm",
    "reachable_home_relative_y_max_mm",
    "pen_down_delta_from_lift_mm",
    "home_joints_deg",
    "user",
    "tool",
    "draw_speed_pct",
    "draw_blend_pct",
    "travel_speed_pct",
    "accel_pct",
}


def _finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DrawingError("%s must be a finite number" % label)
    value = float(value)
    if not math.isfinite(value):
        raise DrawingError("%s must be a finite number" % label)
    return value


def _integer(value, label, low, high):
    if type(value) is not int or not low <= value <= high:
        raise DrawingError("%s must be an integer in %d..%d" % (label, low, high))
    return value


@dataclass(frozen=True)
class DrawingGeometry:
    canvas_width_mm: float
    canvas_height_mm: float
    canvas_top_left_from_home_mm: tuple
    canvas_u_vector_from_home_mm: tuple
    canvas_v_vector_from_home_mm: tuple
    rail_offset_vector_from_home_mm_per_json_mm: tuple
    reachable_home_relative_y_min_mm: float
    reachable_home_relative_y_max_mm: float
    pen_down_delta_from_lift_mm: tuple
    home_joints_deg: tuple
    user: int
    tool: int
    draw_speed_pct: int
    draw_blend_pct: int
    travel_speed_pct: int
    accel_pct: int


@dataclass(frozen=True)
class PenSlot:
    name: str
    joint_deg: tuple


@dataclass(frozen=True)
class PenRack:
    slots: tuple
    change_depth_mm: float
    final_return_depth_mm: float
    gripper_open_mm: float
    gripper_closed_mm: float

    def slot(self, name):
        for slot in self.slots:
            if slot.name == name:
                return slot
        raise DrawingError("unknown pen slot %r" % name)


@dataclass(frozen=True)
class DrawingConfig:
    production_ready: bool
    flat_group_name: str
    group_pen_slots: tuple
    pen_rack: PenRack
    geometry: DrawingGeometry
    canonical_sha256: str

    def pen_slot(self, group_name):
        for name, slot in self.group_pen_slots:
            if name == group_name:
                return self.pen_rack.slot(slot)
        raise DrawingError("group %r has no pen-slot mapping" % group_name)


def _parse_pen_rack(document):
    if not isinstance(document, dict) or set(document) != _PEN_RACK_FIELDS:
        raise DrawingError("pen_rack has unexpected or missing fields")
    raw_slots = document["slots"]
    if not isinstance(raw_slots, dict) or set(raw_slots) != _PEN_SLOT_NAMES:
        raise DrawingError("pen_rack.slots must contain exactly P1, P2, P3 and P4")
    slots = []
    for name in sorted(raw_slots):
        raw_slot = raw_slots[name]
        if not isinstance(raw_slot, dict) or set(raw_slot) != {"joint_deg"}:
            raise DrawingError("pen slot %s must contain exactly joint_deg" % name)
        joints = raw_slot["joint_deg"]
        if not isinstance(joints, list) or len(joints) != 6:
            raise DrawingError("pen slot %s joint_deg must contain six numbers" % name)
        slots.append(
            PenSlot(
                name=name,
                joint_deg=tuple(
                    _finite(value, "pen_rack.slots.%s.joint_deg" % name)
                    for value in joints
                ),
            )
        )
    values = {
        name: _finite(document[name], "pen_rack.%s" % name)
        for name in (
            "change_depth_mm",
            "final_return_depth_mm",
            "gripper_open_mm",
            "gripper_closed_mm",
        )
    }
    if values["change_depth_mm"] <= 0 or values["final_return_depth_mm"] <= 0:
        raise DrawingError("pen rack depths must be positive")
    if values["gripper_closed_mm"] < 0:
        raise DrawingError("gripper_closed_mm must not be negative")
    if values["gripper_open_mm"] <= values["gripper_closed_mm"]:
        raise DrawingError("gripper_open_mm must exceed gripper_closed_mm")
    return PenRack(slots=tuple(slots), **values)


def _vector(value, label):
    if not isinstance(value, list) or len(value) != 3:
        raise DrawingError("%s must contain three finite numbers" % label)
    return tuple(_finite(item, label) for item in value)


def _parse_geometry(raw):
    if not isinstance(raw, dict):
        raise DrawingError("geometry must be an object")
    fields = set(raw)
    if fields == _LEGACY_GEOMETRY_FIELDS:
        width = _finite(raw["canvas_width_mm"], "geometry.canvas_width_mm")
        height = _finite(raw["canvas_height_mm"], "geometry.canvas_height_mm")
        top_left = (
            0.0,
            _finite(raw["user_y_offset_mm"], "geometry.user_y_offset_mm"),
            _finite(raw["user_z_offset_mm"], "geometry.user_z_offset_mm") + height,
        )
        values = {
            "canvas_width_mm": width,
            "canvas_height_mm": height,
            "canvas_top_left_from_home_mm": top_left,
            "canvas_u_vector_from_home_mm": (0.0, width, 0.0),
            "canvas_v_vector_from_home_mm": (0.0, 0.0, -height),
            "rail_offset_vector_from_home_mm_per_json_mm": (0.0, 1.0, 0.0),
            "reachable_home_relative_y_min_mm": _finite(
                raw["reachable_user_y_min_mm"], "geometry.reachable_user_y_min_mm"
            ) - _finite(raw["home_pose_user_y_mm"], "geometry.home_pose_user_y_mm"),
            "reachable_home_relative_y_max_mm": _finite(
                raw["reachable_user_y_max_mm"], "geometry.reachable_user_y_max_mm"
            ) - _finite(raw["home_pose_user_y_mm"], "geometry.home_pose_user_y_mm"),
            "pen_down_delta_from_lift_mm": (
                -_finite(raw["pen_travel_x_mm"], "geometry.pen_travel_x_mm"),
                0.0,
                0.0,
            ),
        }
    elif fields == _HOME_RELATIVE_GEOMETRY_FIELDS:
        values = {
            "canvas_width_mm": _finite(raw["canvas_width_mm"], "geometry.canvas_width_mm"),
            "canvas_height_mm": _finite(raw["canvas_height_mm"], "geometry.canvas_height_mm"),
            "canvas_top_left_from_home_mm": _vector(
                raw["canvas_top_left_from_home_mm"],
                "geometry.canvas_top_left_from_home_mm",
            ),
            "canvas_u_vector_from_home_mm": _vector(
                raw["canvas_u_vector_from_home_mm"],
                "geometry.canvas_u_vector_from_home_mm",
            ),
            "canvas_v_vector_from_home_mm": _vector(
                raw["canvas_v_vector_from_home_mm"],
                "geometry.canvas_v_vector_from_home_mm",
            ),
            "rail_offset_vector_from_home_mm_per_json_mm": _vector(
                raw["rail_offset_vector_from_home_mm_per_json_mm"],
                "geometry.rail_offset_vector_from_home_mm_per_json_mm",
            ),
            "reachable_home_relative_y_min_mm": _finite(
                raw["reachable_home_relative_y_min_mm"],
                "geometry.reachable_home_relative_y_min_mm",
            ),
            "reachable_home_relative_y_max_mm": _finite(
                raw["reachable_home_relative_y_max_mm"],
                "geometry.reachable_home_relative_y_max_mm",
            ),
            "pen_down_delta_from_lift_mm": _vector(
                raw["pen_down_delta_from_lift_mm"],
                "geometry.pen_down_delta_from_lift_mm",
            ),
        }
    else:
        raise DrawingError("geometry has unexpected or missing fields")
    if values["canvas_width_mm"] <= 0 or values["canvas_height_mm"] <= 0:
        raise DrawingError("configured canvas dimensions must be positive")
    if values["reachable_home_relative_y_min_mm"] >= values["reachable_home_relative_y_max_mm"]:
        raise DrawingError("reachable Home-relative Y minimum must be less than maximum")
    if not any(values["pen_down_delta_from_lift_mm"]):
        raise DrawingError("pen_down_delta_from_lift_mm must not be zero")
    joints = raw["home_joints_deg"]
    if not isinstance(joints, list) or len(joints) != 6:
        raise DrawingError("home_joints_deg must contain six numbers")
    return DrawingGeometry(
        **values,
        home_joints_deg=tuple(_finite(value, "home_joints_deg") for value in joints),
        user=_integer(raw["user"], "geometry.user", 0, 9),
        tool=_integer(raw["tool"], "geometry.tool", 0, 9),
        draw_speed_pct=_integer(raw["draw_speed_pct"], "geometry.draw_speed_pct", 1, 100),
        draw_blend_pct=_integer(raw["draw_blend_pct"], "geometry.draw_blend_pct", 0, 100),
        travel_speed_pct=_integer(raw["travel_speed_pct"], "geometry.travel_speed_pct", 1, 100),
        accel_pct=_integer(raw["accel_pct"], "geometry.accel_pct", 1, 100),
    )


def parse_drawing_config(document):
    if not isinstance(document, dict) or set(document) != _TOP_FIELDS:
        raise DrawingError("drawing config has unexpected or missing fields")
    if type(document["production_ready"]) is not bool:
        raise DrawingError("production_ready must be boolean")
    flat_group_name = document["flat_group_name"]
    if not isinstance(flat_group_name, str) or not flat_group_name.strip():
        raise DrawingError("flat_group_name must be a non-empty string")
    pen_map = document["group_pen_slots"]
    if not isinstance(pen_map, dict):
        raise DrawingError("group_pen_slots must be an object")
    slots = []
    for name, slot in pen_map.items():
        if not isinstance(name, str) or not name.strip():
            raise DrawingError("pen mapping names must be non-empty strings")
        if not isinstance(slot, str) or not slot.strip():
            raise DrawingError("pen slot for %r must be configured" % name)
        slots.append((name, slot))

    pen_rack = _parse_pen_rack(document["pen_rack"])
    for name, slot in slots:
        try:
            pen_rack.slot(slot)
        except DrawingError:
            raise DrawingError("pen slot for group %r must be one of P1..P4" % name)

    geometry = _parse_geometry(document["geometry"])
    canonical = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return DrawingConfig(
        production_ready=document["production_ready"],
        flat_group_name=flat_group_name,
        group_pen_slots=tuple(sorted(slots)),
        pen_rack=pen_rack,
        geometry=geometry,
        canonical_sha256=hashlib.sha256(canonical).hexdigest(),
    )


def load_drawing_config(path):
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DrawingError("cannot read drawing config: %s" % type(error).__name__)
    return parse_drawing_config(document)
