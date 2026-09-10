"""Offline AprilTag detection, calibration and console-state tests."""

import json
import pathlib
import sys
import tempfile
import unittest

import cv2
import numpy as np


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "console"))

from runtime_config import (
    ArmConfig,
    CenterDeltaReferenceConfig,
    ChassisConfig,
    ManualChassisConfig,
    LocalizationConfig,
    RuntimeConfig,
    RuntimeConfigError,
    VideoConfig,
    VisionConfig,
    load_runtime_config,
)
from localization import create_localization_state_machine
from localization.state_machine import RailLocalizationStateMachine
from vision.apriltag_localizer import AprilTagBoardLocalizer
from vision.apriltag_center_delta import AprilTagCenterDeltaLocalizer
from vision.calibration import (
    BoardLayout,
    CameraCalibration,
    load_board_layout,
    load_camera_calibration,
)
from web_console.runtime import WebConsoleRuntime


CAMERA = CameraCalibration(
    "synthetic-camera",
    1280,
    720,
    ((900.0, 0.0, 640.0), (0.0, 900.0, 360.0), (0.0, 0.0, 1.0)),
    (0.0, 0.0, 0.0, 0.0, 0.0),
)
BOARD = BoardLayout(
    "synthetic-board",
    "drawing_board",
    "mm",
    "DICT_APRILTAG_36H11",
    {
        0: ((0.0, 0.0, 0.0), (40.0, 0.0, 0.0), (40.0, 40.0, 0.0), (0.0, 40.0, 0.0)),
        1: ((260.0, 0.0, 0.0), (300.0, 0.0, 0.0), (300.0, 40.0, 0.0), (260.0, 40.0, 0.0)),
        2: ((260.0, 160.0, 0.0), (300.0, 160.0, 0.0), (300.0, 200.0, 0.0), (260.0, 200.0, 0.0)),
        3: ((0.0, 160.0, 0.0), (40.0, 160.0, 0.0), (40.0, 200.0, 0.0), (0.0, 200.0, 0.0)),
    },
)


class FakeDetector:
    def __init__(self, corners, ids):
        self.corners = corners
        self.ids = np.asarray(ids, dtype=np.int32).reshape(-1, 1)

    def detectMarkers(self, _image):
        return self.corners, self.ids, []


class CalibrationTests(unittest.TestCase):
    def test_gc4653_example_loads_as_an_unready_native_fov_estimate(self):
        camera = load_camera_calibration(ROOT / "config" / "camera-calibration.example.json")
        self.assertFalse(camera.production_ready)
        self.assertEqual((camera.image_width, camera.image_height), (2560, 1440))
        self.assertAlmostEqual(camera.camera_matrix[0][0], 1498.687444, places=6)
        self.assertAlmostEqual(camera.camera_matrix[1][1], 1509.511392, places=6)
        localizer = AprilTagBoardLocalizer(camera, BOARD)
        scaled = localizer._scaled_camera_matrix(1280, 720)
        self.assertAlmostEqual(scaled[0, 0], 749.343722, places=6)
        self.assertAlmostEqual(scaled[1, 1], 754.755696, places=6)
        self.assertEqual(list(camera.distortion_coefficients), [0.0] * 5)

    def test_endpoint_config_defaults_vision_and_localization_off(self):
        base = json.loads((ROOT / "config" / "console.example.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "console.json"
            path.write_text(json.dumps(base), encoding="utf-8")
            current = load_runtime_config(path)
            self.assertFalse(current.vision.enabled)
            self.assertEqual(current.vision.dictionary, "DICT_APRILTAG_36H11")
            self.assertFalse(current.localization.enabled)
            self.assertEqual(current.localization.settle_time_ms, 2000)
            self.assertEqual(current.localization.rail_axis, "x")
            self.assertEqual(current.localization.json_mm_per_rail_mm, -1.0)

    def test_localization_requires_enabled_complete_vision(self):
        runtime = RuntimeConfig(
            chassis=ChassisConfig("host", 4242, 1.0, "console"),
            manual_chassis=ManualChassisConfig(False, 500, 300, 600, 800),
            arm=ArmConfig("host", 4343, 1.0, "console"),
            video=VideoConfig("", "", 1.0, ""),
            vision=VisionConfig(),
            localization=LocalizationConfig(enabled=True),
        )
        snapshot = create_localization_state_machine(runtime).snapshot()
        self.assertEqual(snapshot["state"], "blocked")
        self.assertEqual(snapshot["reason"], "localization_requires_vision")

    def test_measured_json_loaders_preserve_frame_units_and_corner_order(self):
        camera = {
            "schema_version": 1, "production_ready": True, "calibration_id": "cal-1",
            "image_width": 1280, "image_height": 720,
            "camera_matrix": [[900, 0, 640], [0, 901, 360], [0, 0, 1]],
            "distortion_coefficients": [0, 0, 0, 0, 0],
        }
        board = {
            "schema_version": 1, "production_ready": True, "layout_id": "board-1",
            "frame": "drawing_board", "units": "mm", "dictionary": "DICT_APRILTAG_36H11",
            "corner_order": "top_left_clockwise",
            "tags": {"9": {"corners": [[10, 20, 0], [50, 20, 0], [50, 60, 0], [10, 60, 0]]}},
        }
        with tempfile.TemporaryDirectory() as directory:
            camera_path = pathlib.Path(directory) / "camera.json"
            board_path = pathlib.Path(directory) / "board.json"
            camera_path.write_text(json.dumps(camera), encoding="utf-8")
            board_path.write_text(json.dumps(board), encoding="utf-8")
            loaded_camera = load_camera_calibration(camera_path)
            loaded_board = load_board_layout(board_path)
        self.assertEqual(loaded_camera.camera_matrix[1][1], 901.0)
        self.assertTrue(loaded_camera.production_ready)
        self.assertEqual(loaded_board.units, "mm")
        self.assertTrue(loaded_board.production_ready)
        self.assertEqual(loaded_board.tag_corners[9][0], (10.0, 20.0, 0.0))

    def test_board_layout_accepts_eight_unique_rail_landmarks(self):
        tags = {}
        for tag_id in range(8):
            x = tag_id * 400
            tags[str(tag_id)] = {"corners": [
                [x, 0, 0], [x + 40, 0, 0], [x + 40, 40, 0], [x, 40, 0],
            ]}
        board = {
            "schema_version": 1,
            "production_ready": True,
            "layout_id": "eight-rail-landmarks",
            "frame": "rail_landmarks",
            "units": "mm",
            "dictionary": "DICT_APRILTAG_36H11",
            "corner_order": "top_left_clockwise",
            "tags": tags,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "rail.json"
            path.write_text(json.dumps(board), encoding="utf-8")
            loaded = load_board_layout(path)
        self.assertEqual(sorted(loaded.tag_corners), list(range(8)))


class LocalizerTests(unittest.TestCase):
    def test_center_delta_uses_reference_centers_without_camera_pose(self):
        camera = CameraCalibration(
            CAMERA.calibration_id,
            CAMERA.image_width,
            CAMERA.image_height,
            CAMERA.camera_matrix,
            CAMERA.distortion_coefficients,
            production_ready=False,
        )
        board = BoardLayout(
            BOARD.layout_id,
            BOARD.frame,
            BOARD.units,
            BOARD.dictionary,
            BOARD.tag_corners,
            production_ready=False,
        )
        centers = {
            tag_id: np.asarray(corners, dtype=np.float64)[:, :2].mean(axis=0)
            for tag_id, corners in board.tag_corners.items()
        }
        reference = CenterDeltaReferenceConfig(
            True,
            "synthetic-zero",
            1280,
            720,
            {
                tag_id: (2.0 * point[0] + 100.0, 2.0 * point[1] + 50.0)
                for tag_id, point in centers.items()
            },
            5.0,
            5.0,
        )
        localizer = AprilTagCenterDeltaLocalizer(
            camera,
            board,
            reference,
            min_tag_edge_px=10.0,
            min_visible_tags=2,
        )
        displacement = 75.0
        visible_ids = [1, 2]
        detected = []
        for tag_id in visible_ids:
            center = centers[tag_id]
            pixel_center = np.asarray([
                2.0 * (center[0] - displacement) + 100.0,
                2.0 * center[1] + 50.0,
            ])
            offsets = np.asarray([[-10, -10], [10, -10], [10, 10], [-10, 10]])
            detected.append((pixel_center + offsets).reshape(1, 4, 2))
        localizer._detector = FakeDetector(detected, visible_ids)
        result = localizer.process(np.zeros((720, 1280), dtype=np.uint8), timestamp_ms=456)
        self.assertTrue(result["position_solved"])
        self.assertFalse(result["pose_solved"])
        self.assertTrue(result["accepted"])
        self.assertEqual(result["localization_method"], "center_delta")
        self.assertFalse(result["camera_calibration_ready"])
        self.assertFalse(result["board_layout_ready"])
        self.assertTrue(result["rail_reference_ready"])
        self.assertAlmostEqual(result["rail_position_mm"], displacement, places=5)

        machine = RailLocalizationStateMachine(
            enabled=True,
            rail_axis="x",
            settle_time_ms=0,
            min_valid_samples=1,
            min_visible_tags=2,
        )
        machine.on_chassis_status("enabled_stopped")
        machine.observe_vision(result)
        self.assertAlmostEqual(
            machine.task_context()["rail_position_mm"], displacement, places=5
        )

    def test_opencv_detects_generated_apriltag_and_reports_unknown_without_pose(self):
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
        marker = cv2.aruco.generateImageMarker(dictionary, 7, 180)
        image = np.full((300, 300), 255, dtype=np.uint8)
        image[60:240, 60:240] = marker
        result = AprilTagBoardLocalizer(CAMERA, BOARD).process(image, timestamp_ms=123)
        self.assertEqual(result["detected_count"], 1)
        self.assertEqual(result["observations"][0]["id"], 7)
        self.assertFalse(result["observations"][0]["known"])
        self.assertEqual(result["status"], "unknown_tags")

    def test_oblique_multi_tag_pose_outputs_inverse_matrices_and_confidence(self):
        localizer = AprilTagBoardLocalizer(CAMERA, BOARD, min_confidence=0.45)
        object_groups = [np.asarray(BOARD.tag_corners[tag_id], dtype=np.float64) for tag_id in sorted(BOARD.tag_corners)]
        expected_rvec = np.asarray([[0.42], [-0.28], [0.12]], dtype=np.float64)
        expected_tvec = np.asarray([[-130.0], [-90.0], [760.0]], dtype=np.float64)
        matrix = np.asarray(CAMERA.camera_matrix, dtype=np.float64)
        distortion = np.asarray(CAMERA.distortion_coefficients, dtype=np.float64)
        corners = [cv2.projectPoints(group, expected_rvec, expected_tvec, matrix, distortion)[0].reshape(1, 4, 2) for group in object_groups]
        localizer._detector = FakeDetector(corners, sorted(BOARD.tag_corners))
        result = localizer.process(np.zeros((720, 1280), dtype=np.uint8), timestamp_ms=456)
        self.assertTrue(result["pose_solved"])
        self.assertTrue(result["accepted"])
        self.assertEqual(result["used_ids"], [0, 1, 2, 3])
        self.assertLess(result["reprojection_rmse_px"], 0.01)
        transform = np.asarray(result["T_camera_from_board"])
        inverse = np.asarray(result["T_board_from_camera"])
        np.testing.assert_allclose(transform @ inverse, np.eye(4), atol=1e-3)
        np.testing.assert_allclose(transform[:3, 3], expected_tvec.reshape(3), atol=1e-3)
        self.assertEqual(result["confidence_kind"], "quality_score_not_probability")
        machine = RailLocalizationStateMachine(
            enabled=True,
            rail_axis="x",
            settle_time_ms=0,
            min_valid_samples=1,
            min_visible_tags=2,
        )
        machine.on_chassis_status("enabled_stopped")
        machine.observe_vision(result)
        self.assertAlmostEqual(machine.task_context()["rail_position_mm"], inverse[0, 3], places=6)

    def test_one_known_tag_can_solve_without_a_tag_count_gate(self):
        localizer = AprilTagBoardLocalizer(CAMERA, BOARD, min_confidence=0.4)
        object_points = np.asarray(BOARD.tag_corners[0], dtype=np.float64)
        rvec = np.asarray([[0.2], [0.1], [-0.05]], dtype=np.float64)
        tvec = np.asarray([[-20.0], [-20.0], [500.0]], dtype=np.float64)
        corners = cv2.projectPoints(
            object_points, rvec, tvec, np.asarray(CAMERA.camera_matrix), np.asarray(CAMERA.distortion_coefficients)
        )[0].reshape(1, 4, 2)
        localizer._detector = FakeDetector([corners], [0])
        result = localizer.process(np.zeros((720, 1280), dtype=np.uint8))
        self.assertTrue(result["pose_solved"])
        self.assertTrue(result["accepted"])
        self.assertEqual(result["used_ids"], [0])

    def test_unmeasured_gc4653_and_rectangle_solve_only_a_precalibration_pose(self):
        camera = load_camera_calibration(ROOT / "config" / "camera-calibration.example.json")
        board = load_board_layout(ROOT / "config" / "apriltag-board.example.json")
        localizer = AprilTagBoardLocalizer(camera, board, min_confidence=0.0)
        object_groups = [np.asarray(board.tag_corners[tag_id], dtype=np.float64) for tag_id in sorted(board.tag_corners)]
        rvec = np.asarray([[0.3], [-0.2], [0.1]], dtype=np.float64)
        tvec = np.asarray([[-120.0], [-80.0], [800.0]], dtype=np.float64)
        runtime_matrix = localizer._scaled_camera_matrix(1280, 720)
        corners = [
            cv2.projectPoints(
                group, rvec, tvec, runtime_matrix,
                np.asarray(camera.distortion_coefficients)
            )[0].reshape(1, 4, 2)
            for group in object_groups
        ]
        localizer._detector = FakeDetector(corners, sorted(board.tag_corners))
        result = localizer.process(np.zeros((720, 1280), dtype=np.uint8))
        self.assertTrue(result["pose_solved"])
        self.assertFalse(result["accepted"])
        self.assertEqual(result["status"], "precalibration")
        self.assertEqual(result["error"], "calibration_inputs_unverified")
        self.assertFalse(result["camera_calibration_ready"])
        self.assertFalse(result["board_layout_ready"])


class ConsoleVisionStateTests(unittest.TestCase):
    @staticmethod
    def config():
        return RuntimeConfig(
            chassis=ChassisConfig("", 0, 1.0, "console"),
            manual_chassis=ManualChassisConfig(False, 500, 300, 600, 800),
            arm=ArmConfig("", 0, 1.0, "console"),
            video=VideoConfig("", "", 1.0, ""),
            vision=VisionConfig(enabled=True, stale_after_ms=100),
        )

    def test_accepted_observation_becomes_stale_without_mutating_stored_pose(self):
        clock = [10.0]
        runtime = WebConsoleRuntime(self.config(), start_workers=False, clock=lambda: clock[0])
        try:
            runtime._on_vision_update({
                "enabled": True,
                "status": "accepted",
                "error": "none",
                "observations": [],
                "pose_solved": True,
                "accepted": True,
                "confidence": 0.9,
            })
            self.assertTrue(runtime.snapshot()["vision"]["accepted"])
            clock[0] += 0.2
            stale = runtime.snapshot()["vision"]
            self.assertFalse(stale["accepted"])
            self.assertEqual(stale["status"], "stale")
            clock[0] = 10.0
            self.assertTrue(runtime.snapshot()["vision"]["accepted"])
        finally:
            runtime.close()


if __name__ == "__main__":
    unittest.main()
