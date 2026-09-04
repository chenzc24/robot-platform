"""Strict JSON loaders for camera intrinsics and AprilTag board geometry."""

import json
import math
from dataclasses import dataclass
from pathlib import Path


class VisionCalibrationError(ValueError):
    """Calibration data is missing, ambiguous, or unsafe to use."""


@dataclass(frozen=True)
class CameraCalibration:
    calibration_id: str
    image_width: int
    image_height: int
    camera_matrix: tuple
    distortion_coefficients: tuple
    production_ready: bool = True


@dataclass(frozen=True)
class BoardLayout:
    layout_id: str
    frame: str
    units: str
    dictionary: str
    tag_corners: dict
    production_ready: bool = True


def _read_object(path, label):
    source = Path(path)
    if not source.is_file():
        raise VisionCalibrationError("%s_file_unavailable" % label)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VisionCalibrationError("%s_file_invalid" % label) from error
    if not isinstance(value, dict):
        raise VisionCalibrationError("%s_object_required" % label)
    return value


def _finite_number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise VisionCalibrationError("%s_must_be_finite" % field)
    return float(value)


def _positive_int(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise VisionCalibrationError("%s_must_be_positive_integer" % field)
    return value


def _nonempty_string(value, field):
    if not isinstance(value, str) or not value.strip():
        raise VisionCalibrationError("%s_must_be_nonempty_string" % field)
    return value.strip()


def _boolean(value, field):
    if not isinstance(value, bool):
        raise VisionCalibrationError("%s_must_be_boolean" % field)
    return value


def load_camera_calibration(path):
    raw = _read_object(path, "camera_calibration")
    expected = {
        "schema_version", "production_ready", "calibration_id", "image_width",
        "image_height", "camera_matrix", "distortion_coefficients",
    }
    if set(raw) != expected or raw["schema_version"] != 1:
        raise VisionCalibrationError("camera_calibration_schema_invalid")
    production_ready = _boolean(raw["production_ready"], "camera_calibration.production_ready")
    matrix = raw["camera_matrix"]
    if not isinstance(matrix, list) or len(matrix) != 3 or any(not isinstance(row, list) or len(row) != 3 for row in matrix):
        raise VisionCalibrationError("camera_matrix_shape_invalid")
    camera_matrix = tuple(tuple(_finite_number(value, "camera_matrix") for value in row) for row in matrix)
    image_width = _positive_int(raw["image_width"], "image_width")
    image_height = _positive_int(raw["image_height"], "image_height")
    if camera_matrix[0][0] <= 0 or camera_matrix[1][1] <= 0:
        raise VisionCalibrationError("camera_focal_length_invalid")
    if camera_matrix[2] != (0.0, 0.0, 1.0):
        raise VisionCalibrationError("camera_matrix_last_row_invalid")
    if not 0 <= camera_matrix[0][2] < image_width or not 0 <= camera_matrix[1][2] < image_height:
        raise VisionCalibrationError("camera_principal_point_invalid")
    distortion = raw["distortion_coefficients"]
    if not isinstance(distortion, list) or len(distortion) not in {4, 5, 8, 12, 14}:
        raise VisionCalibrationError("distortion_coefficients_shape_invalid")
    return CameraCalibration(
        calibration_id=_nonempty_string(raw["calibration_id"], "calibration_id"),
        image_width=image_width,
        image_height=image_height,
        camera_matrix=camera_matrix,
        distortion_coefficients=tuple(_finite_number(value, "distortion_coefficients") for value in distortion),
        production_ready=production_ready,
    )


def load_board_layout(path):
    raw = _read_object(path, "board_layout")
    expected = {
        "schema_version", "production_ready", "layout_id", "frame", "units",
        "dictionary", "corner_order", "tags",
    }
    if set(raw) != expected or raw["schema_version"] != 1:
        raise VisionCalibrationError("board_layout_schema_invalid")
    production_ready = _boolean(raw["production_ready"], "board_layout.production_ready")
    if raw["dictionary"] != "DICT_APRILTAG_36H11":
        raise VisionCalibrationError("board_dictionary_unsupported")
    if raw["corner_order"] != "top_left_clockwise":
        raise VisionCalibrationError("board_corner_order_unsupported")
    if raw["units"] != "mm":
        raise VisionCalibrationError("board_units_must_be_mm")
    tags = raw["tags"]
    if not isinstance(tags, dict) or not tags:
        raise VisionCalibrationError("board_tags_required")
    parsed = {}
    for key, value in tags.items():
        try:
            tag_id = int(key)
        except (TypeError, ValueError) as error:
            raise VisionCalibrationError("board_tag_id_invalid") from error
        if str(tag_id) != str(key) or tag_id < 0:
            raise VisionCalibrationError("board_tag_id_invalid")
        if not isinstance(value, dict) or set(value) != {"corners"}:
            raise VisionCalibrationError("board_tag_entry_invalid")
        corners = value["corners"]
        if not isinstance(corners, list) or len(corners) != 4:
            raise VisionCalibrationError("board_tag_corner_count_invalid")
        parsed_corners = []
        for corner in corners:
            if not isinstance(corner, list) or len(corner) != 3:
                raise VisionCalibrationError("board_tag_corner_shape_invalid")
            parsed_corners.append(tuple(_finite_number(axis, "board_tag_corner") for axis in corner))
        edge_lengths = []
        for index in range(4):
            first, second = parsed_corners[index], parsed_corners[(index + 1) % 4]
            edge_lengths.append(math.dist(first, second))
        if min(edge_lengths) <= 0 or max(edge_lengths) / min(edge_lengths) > 1.02:
            raise VisionCalibrationError("board_tag_must_be_square")
        diagonals = (math.dist(parsed_corners[0], parsed_corners[2]), math.dist(parsed_corners[1], parsed_corners[3]))
        if min(diagonals) <= 0 or max(diagonals) / min(diagonals) > 1.02:
            raise VisionCalibrationError("board_tag_must_be_square")
        parsed[tag_id] = tuple(parsed_corners)
    all_z = [corner[2] for corners in parsed.values() for corner in corners]
    if max(all_z) - min(all_z) > 1e-6:
        raise VisionCalibrationError("board_v1_requires_coplanar_tags")
    return BoardLayout(
        layout_id=_nonempty_string(raw["layout_id"], "layout_id"),
        frame=_nonempty_string(raw["frame"], "frame"),
        units="mm",
        dictionary=raw["dictionary"],
        tag_corners=parsed,
        production_ready=production_ready,
    )
