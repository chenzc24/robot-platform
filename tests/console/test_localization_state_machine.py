"""Deterministic L1 checks for one-dimensional rail localization."""

import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "console"))

from localization.state_machine import RailLocalizationStateMachine, LocalizationStateError


def pose(x=0.0, y=0.0, z=0.0):
    return [
        [1.0, 0.0, 0.0, float(x)],
        [0.0, 1.0, 0.0, float(y)],
        [0.0, 0.0, 1.0, float(z)],
        [0.0, 0.0, 0.0, 1.0],
    ]


def vision(sequence, position=130.0, *, accepted=True, ids=(0, 1), calibration="camera-1", layout="rail-1"):
    return {
        "accepted": accepted,
        "pose_solved": accepted,
        "error": "none" if accepted else "no_tags",
        "camera_calibration_ready": True,
        "board_layout_ready": True,
        "calibration_id": calibration,
        "layout_id": layout,
        "board_frame": "rail_landmarks",
        "frame_sequence": sequence,
        "captured_at_ms": 1000 + sequence,
        "used_ids": list(ids),
        "confidence": 0.9,
        "reprojection_rmse_px": 0.5,
        "T_board_from_camera": pose(x=position, y=25.0, z=500.0),
    }


class RailLocalizationTests(unittest.TestCase):
    def setUp(self):
        self.clock = [10.0]
        self.machine = RailLocalizationStateMachine(
            enabled=True,
            rail_axis="x",
            json_axis="x",
            json_origin_rail_position_mm=100.0,
            json_mm_per_rail_mm=-1.0,
            settle_time_ms=1000,
            sample_window_ms=3000,
            min_valid_samples=3,
            min_visible_tags=2,
            max_position_spread_mm=0.25,
            clock=lambda: self.clock[0],
        )

    def settle(self):
        self.machine.on_chassis_status("enabled_stopped")
        self.assertEqual(self.machine.snapshot()["state"], "settling")
        self.clock[0] += 1.0
        self.assertEqual(self.machine.snapshot()["state"], "collecting")

    def lock(self):
        self.settle()
        for sequence, position in enumerate((129.9, 130.0, 130.1), 1):
            self.machine.observe_vision(vision(sequence, position))
            self.clock[0] += 0.1
        return self.machine.snapshot()

    def test_stable_samples_lock_scalar_json_offset(self):
        snapshot = self.lock()
        self.assertTrue(snapshot["valid"])
        self.assertEqual(snapshot["state"], "locked")
        self.assertEqual(snapshot["generation"], 1)
        context = snapshot["context"]
        self.assertEqual(context["mode"], "rail_1d")
        self.assertAlmostEqual(context["rail_position_mm"], 130.0)
        self.assertAlmostEqual(context["rail_delta_from_json_origin_mm"], 30.0)
        self.assertAlmostEqual(context["json_axis_offset_mm"], -30.0)
        self.assertEqual(context["source"]["sample_count"], 3)

    def test_configured_y_axis_and_positive_scale_are_used(self):
        machine = RailLocalizationStateMachine(
            enabled=True,
            rail_axis="y",
            json_axis="y",
            json_origin_rail_position_mm=20.0,
            json_mm_per_rail_mm=2.0,
            settle_time_ms=0,
            min_valid_samples=1,
            min_visible_tags=1,
            clock=lambda: self.clock[0],
        )
        machine.on_chassis_status("enabled_stopped")
        result = vision(1, ids=(7,))
        result["T_board_from_camera"] = pose(x=999.0, y=25.0, z=500.0)
        machine.observe_vision(result)
        context = machine.task_context()
        self.assertEqual(context["rail_position_mm"], 25.0)
        self.assertEqual(context["json_axis_offset_mm"], 10.0)

    def test_changing_visible_tag_ids_does_not_reset_global_layout_window(self):
        self.settle()
        self.machine.observe_vision(vision(1, 130.0, ids=(0, 1)))
        self.machine.observe_vision(vision(2, 130.1, ids=(1, 2)))
        self.machine.observe_vision(vision(3, 129.9, ids=(2, 3)))
        context = self.machine.task_context()
        self.assertEqual(context["source"]["used_ids"], [0, 1, 2, 3])

    def test_invalid_and_duplicate_frames_cannot_fill_window(self):
        self.settle()
        repeated = vision(1, 130.0)
        self.machine.observe_vision(repeated)
        self.machine.observe_vision(vision(2, accepted=False))
        self.machine.observe_vision(repeated)
        snapshot = self.machine.snapshot()
        self.assertEqual(snapshot["state"], "collecting")
        self.assertEqual(snapshot["sample_count"], 1)
        self.assertEqual(snapshot["last_observation_error"], "vision_frame_not_new")

    def test_layout_change_restarts_sample_window(self):
        self.settle()
        self.machine.observe_vision(vision(1, 130.0))
        self.machine.observe_vision(vision(2, 130.0))
        self.machine.observe_vision(vision(3, 130.0, layout="rail-2"))
        snapshot = self.machine.snapshot()
        self.assertEqual(snapshot["state"], "collecting")
        self.assertEqual(snapshot["sample_count"], 1)

    def test_unstable_position_stays_collecting(self):
        self.settle()
        for sequence, position in enumerate((125.0, 130.0, 135.0), 1):
            self.machine.observe_vision(vision(sequence, position))
        snapshot = self.machine.snapshot()
        self.assertEqual(snapshot["state"], "collecting")
        self.assertEqual(snapshot["reason"], "rail_position_unstable")

    def test_sample_window_expires_without_a_new_frame(self):
        self.settle()
        self.machine.observe_vision(vision(1, 130.0))
        self.clock[0] += 3.01
        self.assertEqual(self.machine.snapshot()["sample_count"], 0)

    def test_task_context_is_versioned_and_motion_invalidates_active_task(self):
        generation = self.lock()["generation"]
        context = self.machine.begin_task("draw-1", generation)
        context["json_axis_offset_mm"] = -999
        self.assertAlmostEqual(self.machine.task_context(generation)["json_axis_offset_mm"], -30.0)
        self.machine.on_motion_intent()
        invalid = self.machine.snapshot()
        self.assertFalse(invalid["valid"])
        self.assertEqual(invalid["state"], "moving")
        self.assertEqual(invalid["task"]["last"]["state"], "UNKNOWN")
        with self.assertRaisesRegex(LocalizationStateError, "localization_not_locked"):
            self.machine.task_context(generation)

    def test_task_completion_preserves_lock_and_generation(self):
        generation = self.lock()["generation"]
        self.machine.begin_task("draw-1", generation)
        self.machine.finish_task("draw-1", "DONE", "complete")
        self.assertTrue(self.machine.snapshot()["valid"])
        with self.assertRaisesRegex(LocalizationStateError, "stale_localization_generation"):
            self.machine.begin_task("draw-2", generation + 1)
        with self.assertRaisesRegex(LocalizationStateError, "invalid_localization_generation"):
            self.machine.task_context(True)

    def test_disabled_and_bad_configuration_fail_closed(self):
        disabled = RailLocalizationStateMachine(enabled=False)
        self.assertEqual(disabled.snapshot()["state"], "disabled")
        blocked = RailLocalizationStateMachine(enabled=True, rail_axis="roll")
        blocked.on_motion_intent()
        blocked.on_chassis_unavailable()
        blocked.on_chassis_status("enabled_stopped")
        self.assertEqual(blocked.snapshot()["state"], "blocked")
        with self.assertRaisesRegex(LocalizationStateError, "invalid_rail_axis"):
            blocked.request_relocalization()


if __name__ == "__main__":
    unittest.main()
