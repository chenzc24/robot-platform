"""Deterministic tests for the non-blocking ESP32 line-following core."""

import pathlib
import sys
import unittest


APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "esp32" / "app"
sys.path.insert(0, str(APP_DIR))

from line_following import FAULT, FOLLOWING, IDLE, STATION, LineFollowConfig, LineFollower


class FakeChassis:
    def __init__(self):
        self.state = "enabled_stopped"
        self.calls = []
        self.fail_drive = False
        self.fail_stop = False

    def drive(self, vx, vy, omega):
        self.calls.append(("drive", vx, vy, omega))
        if self.fail_drive:
            raise OSError("drive failed")
        self.state = "moving"

    def stop(self):
        self.calls.append(("stop",))
        if self.fail_stop:
            raise OSError("stop failed")
        if self.state in ("enabled_stopped", "moving"):
            self.state = "enabled_stopped"


class MutableSensors:
    def __init__(self, **values):
        self.values = values

    def __call__(self):
        return dict(self.values)


def samples(line_left=1, line_right=1, station_left=0, station_right=0):
    return {
        "line_left": line_left,
        "line_right": line_right,
        "station_left": station_left,
        "station_right": station_right,
    }


class LineFollowerTests(unittest.TestCase):
    def setUp(self):
        self.chassis = FakeChassis()
        self.sensors = MutableSensors(**samples())
        self.config = LineFollowConfig(
            active_level=1,
            steering_sign=1,
            center_pattern="both_active",
            forward_speed_m_s=0.08,
            correction_speed_m_s=0.04,
            correction_omega_rad_s=0.12,
            station_confirm_ms=100,
            line_loss_timeout_ms=80,
            max_step_gap_ms=50,
        )
        self.follower = LineFollower(self.chassis, self.sensors, self.config)

    def start(self, direction=1):
        result = self.follower.start(direction)
        self.assertEqual(result["state"], FOLLOWING)
        self.assertEqual(self.chassis.calls[-1], ("stop",))

    def test_config_requires_explicit_binary_polarity_and_steering_sign(self):
        with self.assertRaises(ValueError):
            LineFollowConfig(
                active_level=True,
                steering_sign=1,
                center_pattern="both_active",
            )
        with self.assertRaises(ValueError):
            LineFollowConfig(
                active_level=1,
                steering_sign=0,
                center_pattern="both_active",
            )
        with self.assertRaises(ValueError):
            LineFollowConfig(
                active_level=1,
                steering_sign=1,
                center_pattern="both_active",
                forward_speed_m_s=0.61,
            )
        with self.assertRaises(ValueError):
            LineFollowConfig(
                active_level=1,
                steering_sign=1,
                center_pattern="inferred",
            )

    def test_both_inactive_center_pattern_is_supported_explicitly(self):
        config = LineFollowConfig(
            active_level=1,
            steering_sign=1,
            center_pattern="both_inactive",
        )
        sensors = MutableSensors(**samples(line_left=0, line_right=0))
        follower = LineFollower(self.chassis, sensors, config)
        follower.start(1)
        snapshot = follower.step(1000)
        self.assertEqual(snapshot["reason"], "centered")
        self.assertEqual(self.chassis.calls[-1], ("drive", 0.08, 0.0, 0.0))

    def test_start_requires_stopped_enabled_chassis_and_does_not_drive(self):
        self.chassis.state = "disabled"
        with self.assertRaises(RuntimeError):
            self.follower.start(1)
        self.assertEqual(self.chassis.calls, [])

        self.chassis.state = "enabled_stopped"
        snapshot = self.follower.start(-1)
        self.assertEqual(snapshot["direction"], -1)
        self.assertEqual(snapshot["reason"], "awaiting_sensor_sample")
        self.assertFalse(any(call[0] == "drive" for call in self.chassis.calls))

    def test_centered_sample_drives_only_on_configured_axis(self):
        self.start()
        snapshot = self.follower.step(1000)
        self.assertEqual(snapshot["reason"], "centered")
        self.assertEqual(self.chassis.calls[-1], ("drive", 0.08, 0.0, 0.0))

    def test_single_sensor_uses_slower_bounded_yaw_correction(self):
        self.start()
        self.sensors.values = samples(line_left=1, line_right=0)
        left = self.follower.step(1000)
        self.assertEqual(left["reason"], "correcting")
        self.assertEqual(self.chassis.calls[-1], ("drive", 0.04, 0.0, 0.12))

        self.sensors.values = samples(line_left=0, line_right=1)
        right = self.follower.step(1020)
        self.assertEqual(right["reason"], "correcting")
        self.assertEqual(self.chassis.calls[-1], ("drive", 0.04, 0.0, -0.12))

    def test_direction_changes_progress_but_not_explicit_sensor_mapping(self):
        self.start(direction=-1)
        self.sensors.values = samples(line_left=1, line_right=0)
        self.follower.step(1000)
        self.assertEqual(self.chassis.calls[-1], ("drive", -0.04, 0.0, 0.12))

    def test_line_loss_stops_immediately_then_faults_after_timeout(self):
        self.start()
        self.sensors.values = samples(line_left=0, line_right=0)
        first = self.follower.step(1000)
        self.assertEqual(first["state"], FOLLOWING)
        self.assertEqual(first["reason"], "line_missing")
        self.assertEqual(self.chassis.calls[-1], ("stop",))

        second = self.follower.step(1040)
        self.assertEqual(second["state"], FOLLOWING)
        final = self.follower.step(1080)
        self.assertEqual(final["state"], FAULT)
        self.assertEqual(final["reason"], "line_lost")

    def test_reacquired_line_resumes_before_loss_timeout(self):
        self.start()
        self.sensors.values = samples(line_left=0, line_right=0)
        self.follower.step(1000)
        self.sensors.values = samples()
        snapshot = self.follower.step(1040)
        self.assertEqual(snapshot["state"], FOLLOWING)
        self.assertEqual(snapshot["reason"], "centered")
        self.assertEqual(self.chassis.calls[-1], ("drive", 0.08, 0.0, 0.0))

    def test_station_candidate_stops_and_requires_continuous_confirmation(self):
        self.start()
        self.sensors.values = samples(station_left=1, station_right=1)
        candidate = self.follower.step(1000)
        self.assertEqual(candidate["state"], FOLLOWING)
        self.assertEqual(candidate["reason"], "station_candidate")
        self.assertEqual(self.chassis.calls[-1], ("stop",))

        self.follower.step(1050)
        confirmed = self.follower.step(1100)
        self.assertEqual(confirmed["state"], STATION)
        self.assertEqual(confirmed["reason"], "station_confirmed")
        self.assertEqual(self.chassis.state, "enabled_stopped")

    def test_interrupted_station_candidate_must_restart_debounce(self):
        self.start()
        self.sensors.values = samples(station_left=1, station_right=1)
        self.follower.step(1000)
        self.sensors.values = samples()
        self.follower.step(1040)
        self.sensors.values = samples(station_left=1, station_right=1)
        snapshot = self.follower.step(1080)
        self.assertEqual(snapshot["reason"], "station_candidate")
        snapshot = self.follower.step(1120)
        self.assertEqual(snapshot["state"], FOLLOWING)

    def test_stale_scheduler_stops_before_reading_another_sample(self):
        self.start()
        self.follower.step(1000)
        snapshot = self.follower.step(1051)
        self.assertEqual(snapshot["state"], FAULT)
        self.assertEqual(snapshot["reason"], "step_timeout")
        self.assertEqual(self.chassis.calls[-1], ("stop",))

    def test_invalid_sensor_sample_faults_and_stops(self):
        self.start()
        self.sensors.values = {"line_left": 1}
        snapshot = self.follower.step(1000)
        self.assertEqual(snapshot["state"], FAULT)
        self.assertEqual(snapshot["reason"], "sensor_invalid:ValueError")
        self.assertEqual(self.chassis.calls[-1], ("stop",))

    def test_drive_failure_faults_and_attempts_stop(self):
        self.start()
        self.chassis.fail_drive = True
        snapshot = self.follower.step(1000)
        self.assertEqual(snapshot["state"], FAULT)
        self.assertEqual(snapshot["reason"], "drive_failed:OSError")
        self.assertEqual(self.chassis.calls[-1], ("stop",))

    def test_stop_and_fault_reset_keep_lifecycle_explicit(self):
        self.start()
        stopped = self.follower.stop("task_cancelled")
        self.assertEqual(stopped["state"], IDLE)
        self.assertEqual(stopped["reason"], "task_cancelled")

        self.follower.start(1)
        self.follower.step(1000)
        faulted = self.follower.step(1051)
        self.assertEqual(faulted["state"], FAULT)
        still_faulted = self.follower.stop("operator_stop")
        self.assertEqual(still_faulted["state"], FAULT)
        self.assertEqual(still_faulted["reason"], "step_timeout")
        reset = self.follower.reset_fault()
        self.assertEqual(reset["state"], IDLE)
        self.assertEqual(reset["reason"], "fault_reset")


if __name__ == "__main__":
    unittest.main()
