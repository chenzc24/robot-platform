"""Strict robot geometry loading and dependency-free SE(3) helpers."""

import json
import math
from dataclasses import dataclass
from pathlib import Path


class GeometryError(ValueError):
    """Robot geometry or transform data is unsafe or ambiguous."""


@dataclass(frozen=True)
class RobotGeometry:
    geometry_id: str
    base_frame: str
    camera_frame: str
    tool_frame: str
    pen_frame: str
    T_base_from_camera: tuple
    T_tool0_from_pen: tuple
    production_ready: bool = True


def _finite(value, code="transform_must_be_finite"):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise GeometryError(code)
    return float(value)


def _token(value, code):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 80:
        raise GeometryError(code)
    return value.strip()


def _dot(first, second):
    return sum(a * b for a, b in zip(first, second))


def _determinant3(matrix):
    return (
        matrix[0][0] * (matrix[1][1] * matrix[2][2] - matrix[1][2] * matrix[2][1])
        - matrix[0][1] * (matrix[1][0] * matrix[2][2] - matrix[1][2] * matrix[2][0])
        + matrix[0][2] * (matrix[1][0] * matrix[2][1] - matrix[1][1] * matrix[2][0])
    )


def rigid_transform(value, code="invalid_rigid_transform"):
    """Return a validated immutable 4x4 rigid transform."""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise GeometryError(code)
    if any(not isinstance(row, (list, tuple)) or len(row) != 4 for row in value):
        raise GeometryError(code)
    matrix = tuple(tuple(_finite(axis, code) for axis in row) for row in value)
    if any(abs(matrix[3][index]) > 1e-9 for index in range(3)) or abs(matrix[3][3] - 1.0) > 1e-9:
        raise GeometryError(code)
    rotation = tuple(row[:3] for row in matrix[:3])
    for index in range(3):
        if abs(_dot(rotation[index], rotation[index]) - 1.0) > 1e-5:
            raise GeometryError(code)
        for other in range(index + 1, 3):
            if abs(_dot(rotation[index], rotation[other])) > 1e-5:
                raise GeometryError(code)
    if abs(_determinant3(rotation) - 1.0) > 1e-5:
        raise GeometryError(code)
    return matrix


def transform_list(matrix, digits=9):
    return [[round(float(axis), digits) for axis in row] for row in matrix]


def compose(first, second):
    """Compose T_A_from_B and T_B_from_C into T_A_from_C."""
    first = rigid_transform(first)
    second = rigid_transform(second)
    result = []
    for row in range(4):
        result.append(tuple(sum(first[row][axis] * second[axis][column] for axis in range(4)) for column in range(4)))
    return rigid_transform(tuple(result))


def inverse(transform):
    transform = rigid_transform(transform)
    rotation = tuple(tuple(transform[column][row] for column in range(3)) for row in range(3))
    translation = tuple(transform[row][3] for row in range(3))
    inverse_translation = tuple(-_dot(rotation[row], translation) for row in range(3))
    return rigid_transform(tuple(
        tuple(rotation[row]) + (inverse_translation[row],) for row in range(3)
    ) + ((0.0, 0.0, 0.0, 1.0),))


def _quaternion_from_rotation(rotation):
    trace = rotation[0][0] + rotation[1][1] + rotation[2][2]
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        quaternion = (
            0.25 * scale,
            (rotation[2][1] - rotation[1][2]) / scale,
            (rotation[0][2] - rotation[2][0]) / scale,
            (rotation[1][0] - rotation[0][1]) / scale,
        )
    else:
        diagonal = [rotation[index][index] for index in range(3)]
        index = max(range(3), key=lambda item: diagonal[item])
        if index == 0:
            scale = math.sqrt(1.0 + rotation[0][0] - rotation[1][1] - rotation[2][2]) * 2.0
            quaternion = ((rotation[2][1] - rotation[1][2]) / scale, 0.25 * scale,
                          (rotation[0][1] + rotation[1][0]) / scale,
                          (rotation[0][2] + rotation[2][0]) / scale)
        elif index == 1:
            scale = math.sqrt(1.0 + rotation[1][1] - rotation[0][0] - rotation[2][2]) * 2.0
            quaternion = ((rotation[0][2] - rotation[2][0]) / scale,
                          (rotation[0][1] + rotation[1][0]) / scale, 0.25 * scale,
                          (rotation[1][2] + rotation[2][1]) / scale)
        else:
            scale = math.sqrt(1.0 + rotation[2][2] - rotation[0][0] - rotation[1][1]) * 2.0
            quaternion = ((rotation[1][0] - rotation[0][1]) / scale,
                          (rotation[0][2] + rotation[2][0]) / scale,
                          (rotation[1][2] + rotation[2][1]) / scale, 0.25 * scale)
    norm = math.sqrt(_dot(quaternion, quaternion))
    return tuple(axis / norm for axis in quaternion)


def _rotation_from_quaternion(quaternion):
    w, x, y, z = quaternion
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    )


def average_transforms(transforms):
    """Average rigid transforms and return mean plus maximum SE(3) spreads."""
    transforms = [rigid_transform(item) for item in transforms]
    if not transforms:
        raise GeometryError("transform_samples_required")
    count = len(transforms)
    translation = tuple(sum(item[axis][3] for item in transforms) / count for axis in range(3))
    quaternions = [_quaternion_from_rotation(tuple(row[:3] for row in item[:3])) for item in transforms]
    reference = quaternions[0]
    aligned = [tuple(-axis for axis in item) if _dot(reference, item) < 0 else item for item in quaternions]
    quaternion_sum = tuple(sum(item[axis] for item in aligned) for axis in range(4))
    norm = math.sqrt(_dot(quaternion_sum, quaternion_sum))
    if norm <= 1e-12:
        raise GeometryError("rotation_average_ambiguous")
    quaternion = tuple(axis / norm for axis in quaternion_sum)
    rotation = _rotation_from_quaternion(quaternion)
    mean = rigid_transform(tuple(tuple(rotation[row]) + (translation[row],) for row in range(3)) + ((0.0, 0.0, 0.0, 1.0),))
    translation_spread = max(math.dist(translation, tuple(item[axis][3] for axis in range(3))) for item in transforms)
    rotation_spread = max(math.degrees(2.0 * math.acos(min(1.0, abs(_dot(quaternion, item))))) for item in aligned)
    return mean, translation_spread, rotation_spread


def load_robot_geometry(path):
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise GeometryError("robot_geometry_file_unavailable") from error
    except (OSError, json.JSONDecodeError) as error:
        raise GeometryError("robot_geometry_file_invalid") from error
    expected = {
        "schema_version", "production_ready", "geometry_id", "units", "frames",
        "T_base_from_camera", "T_tool0_from_pen",
    }
    if not isinstance(raw, dict) or set(raw) != expected or raw["schema_version"] != 1:
        raise GeometryError("robot_geometry_schema_invalid")
    if not isinstance(raw["production_ready"], bool):
        raise GeometryError("robot_geometry_ready_flag_invalid")
    if raw["units"] != "mm":
        raise GeometryError("robot_geometry_units_must_be_mm")
    frames = raw["frames"]
    if not isinstance(frames, dict) or set(frames) != {"base", "camera", "tool0", "pen"}:
        raise GeometryError("robot_geometry_frames_invalid")
    names = {name: _token(value, "robot_geometry_frame_invalid") for name, value in frames.items()}
    if len(set(names.values())) != 4:
        raise GeometryError("robot_geometry_frames_must_be_distinct")
    return RobotGeometry(
        geometry_id=_token(raw["geometry_id"], "robot_geometry_id_invalid"),
        base_frame=names["base"],
        camera_frame=names["camera"],
        tool_frame=names["tool0"],
        pen_frame=names["pen"],
        T_base_from_camera=rigid_transform(raw["T_base_from_camera"], "T_base_from_camera_invalid"),
        T_tool0_from_pen=rigid_transform(raw["T_tool0_from_pen"], "T_tool0_from_pen_invalid"),
        production_ready=raw["production_ready"],
    )
