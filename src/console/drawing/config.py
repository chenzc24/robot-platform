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
_GEOMETRY_FIELDS = {
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
    user_y_offset_mm: float
    user_z_offset_mm: float
    home_pose_user_y_mm: float
    reachable_user_y_min_mm: float
    reachable_user_y_max_mm: float
    pen_travel_x_mm: float
    home_joints_deg: tuple
    user: int
    tool: int
    draw_speed_pct: int
    draw_blend_pct: int
    travel_speed_pct: object
    accel_pct: object


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


def _optional_integer(value, label, low, high):
    if value is None:
        return None
    return _integer(value, label, low, high)


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

    raw = document["geometry"]
    if not isinstance(raw, dict) or set(raw) != _GEOMETRY_FIELDS:
        raise DrawingError("drawing geometry has unexpected or missing fields")
    numeric = {
        name: _finite(raw[name], "geometry.%s" % name)
        for name in (
            "canvas_width_mm",
            "canvas_height_mm",
            "user_y_offset_mm",
            "user_z_offset_mm",
            "home_pose_user_y_mm",
            "reachable_user_y_min_mm",
            "reachable_user_y_max_mm",
            "pen_travel_x_mm",
        )
    }
    if numeric["canvas_width_mm"] <= 0 or numeric["canvas_height_mm"] <= 0:
        raise DrawingError("configured canvas dimensions must be positive")
    if numeric["pen_travel_x_mm"] <= 0:
        raise DrawingError("pen_travel_x_mm must be positive")
    if numeric["reachable_user_y_min_mm"] >= numeric["reachable_user_y_max_mm"]:
        raise DrawingError("reachable User-Y minimum must be less than maximum")
    joints = raw["home_joints_deg"]
    if not isinstance(joints, list) or len(joints) != 6:
        raise DrawingError("home_joints_deg must contain six numbers")
    joints = tuple(_finite(value, "home_joints_deg") for value in joints)
    geometry = DrawingGeometry(
        **numeric,
        home_joints_deg=joints,
        user=_integer(raw["user"], "geometry.user", 0, 9),
        tool=_integer(raw["tool"], "geometry.tool", 0, 9),
        draw_speed_pct=_integer(raw["draw_speed_pct"], "geometry.draw_speed_pct", 1, 100),
        draw_blend_pct=_integer(raw["draw_blend_pct"], "geometry.draw_blend_pct", 0, 100),
        travel_speed_pct=_optional_integer(
            raw["travel_speed_pct"], "geometry.travel_speed_pct", 1, 100
        ),
        accel_pct=_optional_integer(
            raw["accel_pct"], "geometry.accel_pct", 1, 100
        ),
    )
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
