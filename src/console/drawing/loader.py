"""Strict loaders for grouped Dobot data and flat StrokeReview documents."""

import hashlib
import json
import math
from pathlib import Path

from .models import Canvas, ColorGroup, DrawingError, DrawingJob, Stroke


_AXIS = {"origin": "top-left", "x_positive": "right", "y_positive": "down"}
_CANVAS_FIELDS = {
    "width",
    "height",
    "source_width",
    "source_height",
    "source_aspect_ratio",
    "target_width_mm",
    "target_height_mm",
}
_STROKE_FIELDS = {"id", "order", "points", "closed"}


def _mapping(value, label):
    if not isinstance(value, dict):
        raise DrawingError("%s must be an object" % label)
    return value


def _exact_fields(value, expected, label):
    actual = set(value)
    if actual != set(expected):
        missing = sorted(set(expected) - actual)
        extra = sorted(actual - set(expected))
        raise DrawingError("%s fields mismatch; missing=%s extra=%s" % (label, missing, extra))


def _finite(value, label, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DrawingError("%s must be a finite number" % label)
    value = float(value)
    if not math.isfinite(value):
        raise DrawingError("%s must be a finite number" % label)
    if positive and value <= 0:
        raise DrawingError("%s must be positive" % label)
    return value


def _positive_int(value, label):
    if type(value) is not int or value <= 0:
        raise DrawingError("%s must be a positive integer" % label)
    return value


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise DrawingError("%s must be a non-empty string" % label)
    return value


def _parse_canvas(raw):
    raw = _mapping(raw, "canvas")
    _exact_fields(raw, _CANVAS_FIELDS, "canvas")
    width = _finite(raw["width"], "canvas.width", positive=True)
    height = _finite(raw["height"], "canvas.height", positive=True)
    if width > 1 or height > 1:
        raise DrawingError("normalized canvas width and height must be at most 1")
    return Canvas(
        width=width,
        height=height,
        source_width=_positive_int(raw["source_width"], "canvas.source_width"),
        source_height=_positive_int(raw["source_height"], "canvas.source_height"),
        source_aspect_ratio=_finite(
            raw["source_aspect_ratio"], "canvas.source_aspect_ratio", positive=True
        ),
        target_width_mm=_finite(
            raw["target_width_mm"], "canvas.target_width_mm", positive=True
        ),
        target_height_mm=_finite(
            raw["target_height_mm"], "canvas.target_height_mm", positive=True
        ),
    )


def _parse_strokes(raw_strokes, canvas, group_label, global_ids):
    if not isinstance(raw_strokes, list):
        raise DrawingError("%s.strokes must be an array" % group_label)
    strokes = []
    orders = set()
    for index, item in enumerate(raw_strokes):
        label = "%s.strokes[%d]" % (group_label, index)
        item = _mapping(item, label)
        _exact_fields(item, _STROKE_FIELDS, label)
        stroke_id = _text(item["id"], "%s.id" % label)
        if stroke_id in global_ids:
            raise DrawingError("stroke ids must be unique across the drawing")
        global_ids.add(stroke_id)
        order = _positive_int(item["order"], "%s.order" % label)
        if order in orders:
            raise DrawingError("stroke orders must be unique within each group")
        orders.add(order)
        if type(item["closed"]) is not bool:
            raise DrawingError("%s.closed must be boolean" % label)
        raw_points = item["points"]
        if not isinstance(raw_points, list) or len(raw_points) < 2:
            raise DrawingError("%s.points must contain at least two points" % label)
        points = []
        for point_index, point in enumerate(raw_points):
            point_label = "%s.points[%d]" % (label, point_index)
            if not isinstance(point, list) or len(point) != 2:
                raise DrawingError("%s must be [x, y]" % point_label)
            x = _finite(point[0], "%s.x" % point_label)
            y = _finite(point[1], "%s.y" % point_label)
            if not 0 <= x <= canvas.width or not 0 <= y <= canvas.height:
                raise DrawingError("%s lies outside the normalized canvas" % point_label)
            points.append((x, y))
        strokes.append(
            Stroke(
                id=stroke_id,
                order=order,
                points=tuple(points),
                closed=item["closed"],
            )
        )
    return tuple(sorted(strokes, key=lambda stroke: stroke.order))


def _canonical_document(version, canvas, groups):
    return {
        "version": version,
        "coordinate_space": "normalized",
        "axis": dict(_AXIS),
        "canvas": {
            "width": canvas.width,
            "height": canvas.height,
            "source_width": canvas.source_width,
            "source_height": canvas.source_height,
            "source_aspect_ratio": canvas.source_aspect_ratio,
            "target_width_mm": canvas.target_width_mm,
            "target_height_mm": canvas.target_height_mm,
        },
        "groups": [
            {
                "name": group.name,
                "strokes": [
                    {
                        "id": stroke.id,
                        "order": stroke.order,
                        "points": [list(point) for point in stroke.points],
                        "closed": stroke.closed,
                    }
                    for stroke in group.strokes
                ],
            }
            for group in groups
        ],
    }


def parse_drawing_document(document, flat_group_name="default"):
    """Normalize grouped legacy or flat StrokeReview data into one strict job."""
    document = _mapping(document, "drawing")
    common = {"version", "coordinate_space", "axis", "canvas"}
    shape_fields = set(document) - common
    if shape_fields == {"groups"}:
        source_shape = "grouped"
    elif shape_fields == {"strokes"}:
        source_shape = "flat"
    else:
        raise DrawingError("drawing must contain exactly one of groups or strokes")
    if document["version"] != "1.0":
        raise DrawingError("drawing.version must be 1.0")
    if document["coordinate_space"] != "normalized":
        raise DrawingError("drawing.coordinate_space must be normalized")
    if document["axis"] != _AXIS:
        raise DrawingError("drawing.axis must be top-left with right/down positives")
    canvas = _parse_canvas(document["canvas"])
    global_ids = set()
    groups = []
    if source_shape == "flat":
        name = _text(flat_group_name, "flat_group_name")
        groups.append(
            ColorGroup(
                name=name,
                strokes=_parse_strokes(document["strokes"], canvas, name, global_ids),
            )
        )
    else:
        raw_groups = document["groups"]
        if not isinstance(raw_groups, list) or not raw_groups:
            raise DrawingError("drawing.groups must be a non-empty array")
        names = set()
        for index, item in enumerate(raw_groups):
            label = "groups[%d]" % index
            item = _mapping(item, label)
            _exact_fields(item, {"name", "strokes"}, label)
            name = _text(item["name"], "%s.name" % label)
            if name in names:
                raise DrawingError("group names must be unique")
            names.add(name)
            groups.append(
                ColorGroup(
                    name=name,
                    strokes=_parse_strokes(item["strokes"], canvas, label, global_ids),
                )
            )
    if not groups or not any(group.strokes for group in groups):
        raise DrawingError("drawing contains no strokes")
    groups = tuple(groups)
    canonical = _canonical_document("1.0", canvas, groups)
    encoded = json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return DrawingJob(
        version="1.0",
        canvas=canvas,
        groups=groups,
        source_shape=source_shape,
        canonical_sha256=hashlib.sha256(encoded).hexdigest(),
    )


def canonical_document(job):
    return _canonical_document(job.version, job.canvas, job.groups)


def load_drawing_job(path, flat_group_name="default"):
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DrawingError("cannot read drawing JSON: %s" % type(error).__name__)
    return parse_drawing_document(document, flat_group_name=flat_group_name)
