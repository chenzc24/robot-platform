"""One authoritative PC-side configuration for a physical drawing site."""

import hashlib
import json
import math
from dataclasses import dataclass, replace
from pathlib import Path

from runtime_config import LocalizationConfig, VisionConfig
from vision.calibration import parse_board_layout, parse_camera_calibration

from .config import parse_drawing_config
from .control_modes import parse_drawing_control_config
from .models import DrawingError


_TOP_FIELDS = {
    "schema_version", "production_ready", "image_to_json", "drawing", "rail",
    "relocation", "localization", "vision",
}
_IMAGE_FIELDS = {"fit_mode", "short_edge_margin_mm"}
_DRAWING_FIELDS = {"flat_group_name", "group_pen_slots", "pen_rack", "geometry"}
_RAIL_FIELDS = {
    "physical_start_mm", "physical_travel_mm", "json_origin_rail_position_mm",
    "json_mm_per_rail_mm",
}
_RELOCATION_FIELDS = {"selected_mode", "baseline", "localized_baseline", "advanced"}
_LOCALIZATION_FIELDS = {
    "enabled", "rail_axis", "json_axis", "settle_time_ms", "sample_window_ms",
    "min_valid_samples", "min_visible_tags", "max_position_spread_mm",
}
_VISION_FIELDS = {
    "enabled", "dictionary", "detection_fps", "min_tag_edge_px",
    "max_reprojection_error_px", "min_confidence", "stale_after_ms", "log_path",
    "camera_calibration", "apriltag_board",
}


def _exact(value, fields, label):
    if not isinstance(value, dict) or set(value) != fields:
        raise DrawingError("%s has unexpected or missing fields" % label)
    return value


def _number(value, label, minimum=None, maximum=None, allow_none=False):
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DrawingError("%s must be a finite number" % label)
    value = float(value)
    if not math.isfinite(value):
        raise DrawingError("%s must be a finite number" % label)
    if minimum is not None and value < minimum:
        raise DrawingError("%s is below its minimum" % label)
    if maximum is not None and value > maximum:
        raise DrawingError("%s exceeds its maximum" % label)
    return value


def _integer(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise DrawingError(
            "%s must be an integer in %d..%d" % (label, minimum, maximum)
        )
    return value


@dataclass(frozen=True)
class ImageToJsonConfig:
    fit_mode: str
    short_edge_margin_mm: float


@dataclass(frozen=True)
class RailSiteConfig:
    physical_start_mm: float
    physical_travel_mm: object
    json_origin_rail_position_mm: float
    json_mm_per_rail_mm: float


@dataclass(frozen=True)
class DrawingSiteConfig:
    production_ready: bool
    image_to_json: ImageToJsonConfig
    drawing: object
    control: object
    rail: RailSiteConfig
    localization: LocalizationConfig
    vision: VisionConfig
    camera_calibration: object
    apriltag_board: object
    canonical_sha256: str

    def apply_runtime(self, runtime):
        return replace(runtime, vision=self.vision, localization=self.localization)

def parse_drawing_site_config(document):
    _exact(document, _TOP_FIELDS, "drawing site config")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise DrawingError("unsupported drawing site schema")
    if type(document["production_ready"]) is not bool:
        raise DrawingError("production_ready must be boolean")
    image = _exact(document["image_to_json"], _IMAGE_FIELDS, "image_to_json")
    if image["fit_mode"] != "contain":
        raise DrawingError("image_to_json.fit_mode must be contain")
    drawing_raw = _exact(document["drawing"], _DRAWING_FIELDS, "drawing")
    drawing = parse_drawing_config({
        "production_ready": document["production_ready"],
        **drawing_raw,
    })
    margin = _number(
        image["short_edge_margin_mm"], "image_to_json.short_edge_margin_mm", 0.0
    )
    if margin * 2 >= min(
        drawing.geometry.canvas_width_mm, drawing.geometry.canvas_height_mm
    ):
        raise DrawingError("image_to_json.short_edge_margin_mm leaves no drawable area")

    rail_raw = _exact(document["rail"], _RAIL_FIELDS, "rail")
    rail = RailSiteConfig(
        physical_start_mm=_number(
            rail_raw["physical_start_mm"], "rail.physical_start_mm"
        ),
        physical_travel_mm=_number(
            rail_raw["physical_travel_mm"], "rail.physical_travel_mm", 0.001,
            allow_none=True,
        ),
        json_origin_rail_position_mm=_number(
            rail_raw["json_origin_rail_position_mm"],
            "rail.json_origin_rail_position_mm",
        ),
        json_mm_per_rail_mm=_number(
            rail_raw["json_mm_per_rail_mm"], "rail.json_mm_per_rail_mm", -10.0, 10.0
        ),
    )
    if rail.json_mm_per_rail_mm == 0:
        raise DrawingError("rail.json_mm_per_rail_mm must be nonzero")

    relocation = _exact(document["relocation"], _RELOCATION_FIELDS, "relocation")
    control = parse_drawing_control_config({
        "version": 3,
        "production_ready": document["production_ready"],
        "json_mm_per_rail_mm": rail.json_mm_per_rail_mm,
        **relocation,
    })

    localization_raw = _exact(
        document["localization"], _LOCALIZATION_FIELDS, "localization"
    )
    if type(localization_raw["enabled"]) is not bool:
        raise DrawingError("localization.enabled must be boolean")
    if localization_raw["rail_axis"] not in {"x", "y", "z"}:
        raise DrawingError("localization.rail_axis is invalid")
    if localization_raw["json_axis"] not in {"x", "y"}:
        raise DrawingError("localization.json_axis is invalid")
    localization = LocalizationConfig(
        enabled=localization_raw["enabled"],
        rail_axis=localization_raw["rail_axis"],
        json_axis=localization_raw["json_axis"],
        json_origin_rail_position_mm=rail.json_origin_rail_position_mm,
        json_mm_per_rail_mm=rail.json_mm_per_rail_mm,
        settle_time_ms=_integer(localization_raw["settle_time_ms"], "localization.settle_time_ms", 0, 60_000),
        sample_window_ms=_integer(localization_raw["sample_window_ms"], "localization.sample_window_ms", 100, 60_000),
        min_valid_samples=_integer(localization_raw["min_valid_samples"], "localization.min_valid_samples", 1, 100),
        min_visible_tags=_integer(localization_raw["min_visible_tags"], "localization.min_visible_tags", 1, 100),
        max_position_spread_mm=_number(localization_raw["max_position_spread_mm"], "localization.max_position_spread_mm", 0.001, 100.0),
    )

    vision_raw = _exact(document["vision"], _VISION_FIELDS, "vision")
    if type(vision_raw["enabled"]) is not bool:
        raise DrawingError("vision.enabled must be boolean")
    if localization.enabled and not vision_raw["enabled"]:
        raise DrawingError("localization requires vision.enabled")
    if not isinstance(vision_raw["log_path"], str):
        raise DrawingError("vision.log_path must be a string")
    camera = parse_camera_calibration(vision_raw["camera_calibration"])
    board = parse_board_layout(vision_raw["apriltag_board"])
    if vision_raw["dictionary"] != board.dictionary:
        raise DrawingError("vision dictionary does not match AprilTag board")
    vision = VisionConfig(
        enabled=vision_raw["enabled"],
        dictionary=vision_raw["dictionary"],
        detection_fps=_number(vision_raw["detection_fps"], "vision.detection_fps", 0.2, 30.0),
        min_tag_edge_px=_number(vision_raw["min_tag_edge_px"], "vision.min_tag_edge_px", 4.0, 1000.0),
        max_reprojection_error_px=_number(vision_raw["max_reprojection_error_px"], "vision.max_reprojection_error_px", 0.1, 100.0),
        min_confidence=_number(vision_raw["min_confidence"], "vision.min_confidence", 0.0, 1.0),
        stale_after_ms=_integer(vision_raw["stale_after_ms"], "vision.stale_after_ms", 100, 60_000),
        log_path=vision_raw["log_path"].strip(),
        board_layout=board,
        camera_calibration=camera,
    )
    canonical = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return DrawingSiteConfig(
        production_ready=document["production_ready"],
        image_to_json=ImageToJsonConfig("contain", margin),
        drawing=drawing,
        control=control,
        rail=rail,
        localization=localization,
        vision=vision,
        camera_calibration=camera,
        apriltag_board=board,
        canonical_sha256=hashlib.sha256(canonical).hexdigest(),
    )


def load_drawing_site_config(path):
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DrawingError("cannot read drawing site config: %s" % type(error).__name__)
    return parse_drawing_site_config(document)
