"""Computer-side calibrated vision for the robot console."""

from .apriltag_localizer import AprilTagBoardLocalizer
from .board_calibration import (
    BoardCalibrationError,
    CenterAnchorLayout,
    detect_apriltag_pixels,
    parse_center_anchor_layout,
    solve_board_layout,
)
from .calibration import BoardLayout, CameraCalibration, VisionCalibrationError, load_board_layout, load_camera_calibration

__all__ = [
    "AprilTagBoardLocalizer",
    "BoardCalibrationError",
    "BoardLayout",
    "CameraCalibration",
    "CenterAnchorLayout",
    "VisionCalibrationError",
    "detect_apriltag_pixels",
    "load_board_layout",
    "load_camera_calibration",
    "parse_center_anchor_layout",
    "solve_board_layout",
]
