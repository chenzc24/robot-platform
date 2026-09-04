"""Deterministic L1 checks for localization locking and task handoff."""

import json
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "console"))

from localization.geometry import (
    GeometryError,
    RobotGeometry,
    average_transforms,
    compose,
    inverse,
    load_robot_geometry,
)
from localization.state_machine import LocalizationLockStateMachine, LocalizationStateError


IDENTITY = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)


def translated(x=0.0, y=0.0, z=0.0):
    return (
        (1.0, 0.0, 0.0, float(x)),
        (0.0, 1.0, 0.0, float(y)),
        (0.0, 0.0, 1.0, float(z)),
        (0.0, 0.0, 0.0, 1.0),
    )


def geometry(ready=True):
    return RobotGeometry(
        "geometry-1", "base", "camera", "tool0", "pen",
        translated(100, 0, 0), translated(0, 0, 25), ready,
    )


def vision(sequence, x=10.0, *, accepted=True, ids=(0, 1), calibration="camera-1", layout="board-1"):
    return {
        "accepted": accepted,
        "pose_solved": accepted,
        "error": "none" if accepted else "no_tags",
        "camera_calibration_ready": True,
        "board_layout_ready": True,
        "calibration_id": calibration,
        "layout_id": layout,
        "board_frame": "drawing_board",
        "frame_sequence": sequence,
        "captured_at_ms": 1000 + sequence,
        "used_ids": list(ids),
        "confidence": 0.9,
        "reprojection_rmse_px": 0.5,
        "T_camera_from_board": [list(row) for row in translated(x, 20, 30)],
    }


class GeometryTests(unittest.TestCase):
    def test_example_is_explicitly_unready_and_matrices_are_rigid(self):
        loaded = load_robot_geometry(ROOT / "config" / "robot-geometry.example.json")
        self.assertFalse(loaded.production_ready)
        self.assertEqual(loaded.base_frame, "robot_base_user0")
        self.assertEqual(compose(loaded.T_base_from_camera, IDENTITY), IDENTITY)

    def test_loader_rejects_non_rigid_and_duplicate_frames(self):
        raw = json.loads((ROOT / "config" / "robot-geometry.example.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "geometry.json"
            raw["T_base_from_camera"][0][0] = 2
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(GeometryError, "T_base_from_camera_invalid"):
                load_robot_geometry(path)
            raw = json.loads((ROOT / "config" / "robot-geometry.example.json").read_text(encoding="utf-8"))
            raw["frames"]["camera"] = raw["frames"]["base"]
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(GeometryError, "frames_must_be_distinct"):
                load_robot_geometry(path)

    def test_compose_inverse_and_pose_average(self):
        combined = compose(translated(100, 0, 0), translated(10, 20, 30))
        self.assertEqual(combined, translated(110, 20, 30))
        self.assertEqual(compose(combined, inverse(combined)), IDENTITY)
        mean, translation_spread, rotation_spread = average_transforms([
            translated(9.9, 20, 30), translated(10, 20, 30), translated(10.1, 20, 30),
        ])
        self.assertAlmostEqual(mean[0][3], 10.0)
        self.assertAlmostEqual(translation_spread, 0.1)
        self.assertAlmostEqual(rotation_spread, 0.0)


class StateMachineTests(unittest.TestCase):
    def setUp(self):
        self.clock = [10.0]
        self.machine = LocalizationLockStateMachine(
            enabled=True,
            geometry=geometry(),
            settle_time_ms=1000,
            sample_window_ms=3000,
            min_valid_samples=3,
            min_visible_tags=2,
            max_translation_spread_mm=0.25,
            max_rotation_spread_deg=0.5,
            clock=lambda: self.clock[0],
        )

    def settle(self):
        self.machine.on_chassis_status("enabled_stopped")
        self.assertEqual(self.machine.snapshot()["state"], "settling")
        self.clock[0] += 1.0
        self.assertEqual(self.machine.snapshot()["state"], "collecting")

    def lock(self):
        self.settle()
        for sequence, x in enumerate((9.9, 10.0, 10.1), 1):
            self.machine.observe_vision(vision(sequence, x))
            self.clock[0] += 0.1
        return self.machine.snapshot()

    def test_stopped_stable_samples_lock_composed_context(self):
        snapshot = self.lock()
        self.assertTrue(snapshot["valid"])
        self.assertEqual(snapshot["state"], "locked")
        self.assertEqual(snapshot["generation"], 1)
        context = snapshot["context"]
        self.assertAlmostEqual(context["T_base_from_board"][0][3], 110.0)
        self.assertEqual(context["T_tool0_from_pen"][2][3], 25.0)
        self.assertEqual(context["frames"]["board"], "drawing_board")
        self.assertEqual(context["source"]["sample_count"], 3)

    def test_invalid_frames_do_not_erase_recent_valid_window(self):
        self.settle()
        self.machine.observe_vision(vision(1, 10.0))
        self.machine.observe_vision(vision(2, accepted=False))
        self.machine.observe_vision(vision(3, 10.1))
        self.machine.observe_vision(vision(4, 9.9))
        self.assertEqual(self.machine.snapshot()["state"], "locked")

    def test_duplicate_frame_cannot_satisfy_multi_frame_lock(self):
        self.settle()
        repeated = vision(1, 10.0)
        self.machine.observe_vision(repeated)
        self.machine.observe_vision(repeated)
        self.machine.observe_vision(repeated)
        snapshot = self.machine.snapshot()
        self.assertEqual(snapshot["state"], "collecting")
        self.assertEqual(snapshot["sample_count"], 1)
        self.assertEqual(snapshot["last_observation_error"], "vision_frame_not_new")

    def test_source_change_restarts_sample_window(self):
        self.settle()
        self.machine.observe_vision(vision(1, 10.0))
        self.machine.observe_vision(vision(2, 10.0))
        self.machine.observe_vision(vision(3, 10.0, calibration="camera-2"))
        snapshot = self.machine.snapshot()
        self.assertEqual(snapshot["state"], "collecting")
        self.assertEqual(snapshot["sample_count"], 1)

    def test_unstable_samples_stay_collecting(self):
        self.settle()
        for sequence, x in enumerate((0.0, 2.0, 4.0), 1):
            self.machine.observe_vision(vision(sequence, x))
        snapshot = self.machine.snapshot()
        self.assertEqual(snapshot["state"], "collecting")
        self.assertEqual(snapshot["reason"], "vision_pose_unstable")

    def test_sample_window_expires_without_a_new_frame(self):
        self.settle()
        self.machine.observe_vision(vision(1, 10.0))
        self.assertEqual(self.machine.snapshot()["sample_count"], 1)
        self.clock[0] += 3.01
        self.assertEqual(self.machine.snapshot()["sample_count"], 0)

    def test_task_context_is_versioned_and_motion_invalidates_active_task(self):
        snapshot = self.lock()
        generation = snapshot["generation"]
        context = self.machine.begin_task("draw-1", generation)
        context["T_base_from_board"][0][3] = -999
        self.assertAlmostEqual(self.machine.task_context(generation)["T_base_from_board"][0][3], 110.0)
        self.machine.on_motion_intent()
        invalid = self.machine.snapshot()
        self.assertFalse(invalid["valid"])
        self.assertEqual(invalid["state"], "moving")
        self.assertEqual(invalid["task"]["last"]["state"], "UNKNOWN")
        with self.assertRaisesRegex(LocalizationStateError, "localization_not_locked"):
            self.machine.task_context(generation)

    def test_task_completion_preserves_locked_transform(self):
        generation = self.lock()["generation"]
        self.machine.begin_task("draw-1", generation)
        self.machine.finish_task("draw-1", "DONE", "four_strokes")
        snapshot = self.machine.snapshot()
        self.assertTrue(snapshot["valid"])
        self.assertIsNone(snapshot["task"]["active"])
        self.assertEqual(snapshot["task"]["last"]["state"], "DONE")
        with self.assertRaisesRegex(LocalizationStateError, "stale_localization_generation"):
            self.machine.begin_task("draw-2", generation + 1)
        with self.assertRaisesRegex(LocalizationStateError, "invalid_localization_generation"):
            self.machine.task_context(True)

    def test_disabled_and_unready_geometry_fail_closed(self):
        disabled = LocalizationLockStateMachine(enabled=False)
        self.assertEqual(disabled.snapshot()["state"], "disabled")
        blocked = LocalizationLockStateMachine(enabled=True, geometry=geometry(False))
        blocked.on_motion_intent()
        self.assertEqual(blocked.snapshot()["state"], "blocked")
        blocked.on_chassis_unavailable()
        self.assertEqual(blocked.snapshot()["state"], "blocked")
        blocked.on_chassis_status("enabled_stopped")
        self.assertEqual(blocked.snapshot()["state"], "blocked")
        with self.assertRaisesRegex(LocalizationStateError, "robot_geometry_unverified"):
            blocked.request_relocalization()


if __name__ == "__main__":
    unittest.main()
