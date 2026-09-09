"""Synthetic checks for observation-only planar AprilTag board calibration."""

import json
import pathlib
import sys
import unittest

import cv2
import numpy as np


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "console"))

from vision.board_calibration import (
    BoardCalibrationError,
    detect_apriltag_pixels,
    parse_center_anchor_layout,
    solve_board_layout,
)
from vision.calibration import BoardLayout, parse_board_layout


def tag(x, y, size=40.0):
    return np.asarray(
        [[x, y], [x + size, y], [x + size, y + size], [x, y + size]],
        dtype=np.float64,
    )


WORLD = {
    0: tag(0, 0),
    1: tag(220, 0),
    2: tag(440, 0),
    3: tag(660, 0),
    4: tag(0, 160),
    5: tag(220, 160),
    6: tag(440, 160),
    7: tag(660, 160),
}


def corners3(points):
    return tuple((float(x), float(y), 0.0) for x, y in points)


def rotate_tag(points, degrees):
    center = points.mean(axis=0)
    radians = np.deg2rad(degrees)
    rotation = np.asarray([
        [np.cos(radians), -np.sin(radians)],
        [np.sin(radians), np.cos(radians)],
    ])
    return (points - center) @ rotation.T + center


ANCHORS = BoardLayout(
    "measured-four-corners",
    "drawing_board",
    "mm",
    "DICT_APRILTAG_36H11",
    {tag_id: corners3(WORLD[tag_id]) for tag_id in (0, 3, 4, 7)},
    False,
)

CENTER_ANCHORS = parse_center_anchor_layout({
    "schema_version": 1,
    "layout_id": "measured-center-anchors",
    "frame": "drawing_board",
    "units": "mm",
    "dictionary": "DICT_APRILTAG_36H11",
    "tag_size_mm": 40.0,
    "anchors": {
        str(tag_id): {"center": [*WORLD[tag_id].mean(axis=0).tolist(), 0.0]}
        for tag_id in (0, 3, 4, 7)
    },
})


def project(points, matrix):
    return cv2.perspectiveTransform(points.reshape(1, -1, 2), matrix).reshape(-1, 2)


def synthetic_observations(world=WORLD):
    rng = np.random.default_rng(20260909)
    frames = []
    groups = ((0, 1, 4, 5), (1, 2, 5, 6), (2, 3, 6, 7))
    for station, visible in enumerate(groups):
        for sample in range(5):
            matrix = np.asarray([
                [1.55 + 0.01 * sample, 0.08, 120.0 - station * 300.0],
                [0.03, 1.48 - 0.005 * sample, 90.0 + sample],
                [0.00008 * (station + 1), -0.00005, 1.0],
            ])
            observations = []
            for tag_id in visible:
                pixels = project(world[tag_id], matrix)
                pixels += rng.normal(0.0, 0.03, pixels.shape)
                observations.append({"id": tag_id, "corners_px": pixels.tolist()})
            frames.append({"station": "stop-%d" % station, "observations": observations})
    return {
        "schema_version": 1,
        "dictionary": "DICT_APRILTAG_36H11",
        "frames": frames,
    }


class BoardCalibrationTests(unittest.TestCase):
    def test_supplied_center_anchor_example_preserves_centers_and_side_length(self):
        raw = json.loads(
            (ROOT / "config" / "apriltag-center-anchors.example.json").read_text(
                encoding="utf-8"
            )
        )
        anchors = parse_center_anchor_layout(raw)

        self.assertEqual(anchors.tag_size_mm, 37.5)
        self.assertEqual(sorted(anchors.anchor_centers), [0, 1, 2, 3])
        np.testing.assert_allclose(anchors.anchor_centers[0], [0.0, 0.0, 0.0])
        np.testing.assert_allclose(anchors.anchor_centers[3], [1000.0, 300.0, 0.0])

    def test_capture_detector_records_decoded_id_and_four_pixel_corners(self):
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
        marker = cv2.aruco.generateImageMarker(dictionary, 17, 180)
        image = np.full((300, 300), 255, dtype=np.uint8)
        image[60:240, 60:240] = marker

        result = detect_apriltag_pixels(image)

        self.assertEqual((result["image_width"], result["image_height"]), (300, 300))
        self.assertEqual([item["id"] for item in result["observations"]], [17])
        self.assertEqual(np.asarray(result["observations"][0]["corners_px"]).shape, (4, 2))

    def test_four_anchors_expand_to_eight_tag_layout_without_camera_intrinsics(self):
        board, report = solve_board_layout(
            ANCHORS,
            synthetic_observations(),
            target_ids=range(8),
            layout_id="eight-tag-test",
            min_samples_per_tag=3,
        )

        parsed = parse_board_layout(board)
        self.assertFalse(parsed.production_ready)
        self.assertEqual(sorted(parsed.tag_corners), list(range(8)))
        self.assertEqual(report["anchor_ids"], [0, 3, 4, 7])
        self.assertEqual(report["estimated_ids"], [1, 2, 5, 6])
        self.assertEqual(report["status"], "review_required")
        self.assertLess(report["cross_validated_corner_rmse_mm"], 0.2)

        for tag_id in (0, 3, 4, 7):
            np.testing.assert_allclose(
                np.asarray(parsed.tag_corners[tag_id]),
                np.column_stack((WORLD[tag_id], np.zeros(4))),
                atol=1e-9,
            )
        for tag_id in (1, 2, 5, 6):
            np.testing.assert_allclose(
                np.asarray(parsed.tag_corners[tag_id])[:, :2],
                WORLD[tag_id],
                atol=0.2,
            )
            self.assertGreaterEqual(report["tags"][str(tag_id)]["accepted_frame_count"], 3)
            self.assertGreaterEqual(report["tags"][str(tag_id)]["accepted_station_count"], 2)

    def test_center_anchors_fix_only_centers_and_fit_anchor_rotations(self):
        angles = {
            0: 1.0, 1: -0.5, 2: 0.75, 3: -1.0,
            4: 1.5, 5: -0.8, 6: 0.6, 7: -1.25,
        }
        rotated_world = {
            tag_id: rotate_tag(points, angles[tag_id])
            for tag_id, points in WORLD.items()
        }

        board, report = solve_board_layout(
            CENTER_ANCHORS,
            synthetic_observations(rotated_world),
            target_ids=range(8),
            layout_id="center-anchor-test",
            min_samples_per_tag=3,
            outlier_threshold_mm=8.0,
            refinement_iterations=30,
        )

        parsed = parse_board_layout(board)
        self.assertEqual(
            report["anchor_constraint"],
            "measured_centers_with_fitted_in_plane_rotation",
        )
        for tag_id in range(8):
            np.testing.assert_allclose(
                np.asarray(parsed.tag_corners[tag_id])[:, :2],
                rotated_world[tag_id],
                atol=0.5,
            )
        for tag_id in (0, 3, 4, 7):
            np.testing.assert_allclose(
                np.asarray(parsed.tag_corners[tag_id])[:, :2].mean(axis=0),
                rotated_world[tag_id].mean(axis=0),
                atol=1e-6,
            )
            self.assertEqual(
                report["tags"][str(tag_id)]["kind"],
                "measured_center_anchor_fitted_rotation",
            )
        self.assertLess(report["bundle_reprojection_rmse_px"], 0.1)

    def test_target_must_be_connected_to_an_anchor_by_a_co_visible_frame(self):
        document = {
            "schema_version": 1,
            "dictionary": "DICT_APRILTAG_36H11",
            "frames": [
                {"observations": [{"id": 0, "corners_px": WORLD[0].tolist()}]},
                {"observations": [{"id": 8, "corners_px": tag(300, 80).tolist()}]},
            ],
        }
        with self.assertRaisesRegex(BoardCalibrationError, "not_connected_to_anchors:8"):
            solve_board_layout(ANCHORS, document, target_ids=[0, 3, 4, 7, 8])


if __name__ == "__main__":
    unittest.main()
