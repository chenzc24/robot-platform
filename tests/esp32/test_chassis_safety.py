"""Deterministic safety tests for the ESP32 chassis core."""

import math
import pathlib
import sys
import unittest


APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "esp32" / "app"
sys.path.insert(0, str(APP_DIR))

import main as app_main
from chassis_control import (
    DISABLED,
    ENABLED_STOPPED,
    FAULT,
    MOVING,
    ChassisStateError,
    SafeMecanumChassis,
)


class FakeMotorBus:
    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    def _call(self, name, *args):
        self.calls.append((name,) + args)
        if self.fail_on == name:
            raise OSError("injected %s failure" % name)

    def prepare_speed_mode(self, motor_ids):
        self._call("prepare_speed_mode", tuple(motor_ids))

    def set_acc(self, motor_id, value):
        self._call("set_acc", motor_id, value)

    def set_speed(self, motor_id, value):
        self._call("set_speed", motor_id, value)

    def stop_all(self, motor_ids):
        self._call("stop_all", tuple(motor_ids))

    def disable_all(self, motor_ids):
        self._call("disable_all", tuple(motor_ids))


class RunModeTests(unittest.TestCase):
    def test_safe_idle_is_the_only_supported_mode(self):
        self.assertEqual(app_main.normalize_run_mode("safe_idle"), "safe_idle")
        self.assertEqual(app_main.normalize_run_mode("ps2"), "safe_idle")
        self.assertEqual(app_main.normalize_run_mode("idle"), "safe_idle")
        self.assertEqual(app_main.normalize_run_mode(None), "safe_idle")


class ChassisStateTests(unittest.TestCase):
    def setUp(self):
        self.bus = FakeMotorBus()
        self.chassis = SafeMecanumChassis(self.bus)

    def test_stop_is_not_skipped_while_disabled(self):
        self.chassis.stop()
        self.assertEqual(self.chassis.state, DISABLED)
        self.assertEqual(self.bus.calls, [("stop_all", (1, 2, 3, 4))])

    def test_drive_is_rejected_while_disabled(self):
        with self.assertRaises(ChassisStateError):
            self.chassis.drive(0.1, 0.0, 0.0)
        self.assertFalse(any(call[0] == "set_speed" for call in self.bus.calls))

    def test_enable_zeroes_before_and_after_driver_setup(self):
        self.chassis.enable_motors()
        self.assertEqual(self.chassis.state, ENABLED_STOPPED)
        self.assertEqual(
            [call[0] for call in self.bus.calls],
            ["disable_all", "stop_all", "prepare_speed_mode", "stop_all"],
        )

    def test_enable_is_rejected_unless_disabled(self):
        self.chassis.enable_motors()
        with self.assertRaises(ChassisStateError):
            self.chassis.enable_motors()

    def test_drive_transitions_to_moving_with_four_bounded_targets(self):
        self.chassis.enable_motors()
        self.bus.calls.clear()
        wheel_speeds = self.chassis.drive(99.0, 99.0, 99.0)
        speed_calls = [call for call in self.bus.calls if call[0] == "set_speed"]
        motor_limit = 200.0 * 2.0 * math.pi / 60.0
        self.assertEqual(self.chassis.state, MOVING)
        self.assertEqual(len(speed_calls), 4)
        self.assertLessEqual(max(abs(value) for value in wheel_speeds), motor_limit)

    def test_zero_drive_sends_stop_and_returns_to_enabled_stopped(self):
        self.chassis.enable_motors()
        self.chassis.drive(0.1, 0.0, 0.0)
        self.bus.calls.clear()
        result = self.chassis.drive(0.0, 0.0, 0.0)
        self.assertEqual(result, (0.0, 0.0, 0.0, 0.0))
        self.assertEqual(self.chassis.state, ENABLED_STOPPED)
        self.assertEqual(self.bus.calls, [("stop_all", (1, 2, 3, 4))])

    def test_disable_then_drive_is_rejected(self):
        self.chassis.enable_motors()
        self.chassis.disable()
        self.assertEqual(self.chassis.state, DISABLED)
        with self.assertRaises(ChassisStateError):
            self.chassis.drive_wheel_speeds(1.0, 1.0, 1.0, 1.0)

    def test_enable_failure_enters_fault_and_attempts_safe_output(self):
        bus = FakeMotorBus(fail_on="prepare_speed_mode")
        chassis = SafeMecanumChassis(bus)
        with self.assertRaises(OSError):
            chassis.enable_motors()
        self.assertEqual(chassis.state, FAULT)
        self.assertIn("stop_all", [call[0] for call in bus.calls])
        self.assertIn("disable_all", [call[0] for call in bus.calls])

    def test_drive_failure_enters_fault_and_attempts_safe_output(self):
        bus = FakeMotorBus(fail_on="set_speed")
        chassis = SafeMecanumChassis(bus)
        chassis.enable_motors()
        with self.assertRaises(OSError):
            chassis.drive(0.1, 0.0, 0.0)
        self.assertEqual(chassis.state, FAULT)
        self.assertIn("stop_all", [call[0] for call in bus.calls])
        self.assertIn("disable_all", [call[0] for call in bus.calls])

    def test_disable_failure_leaves_fault_state(self):
        bus = FakeMotorBus(fail_on="disable_all")
        chassis = SafeMecanumChassis(bus)
        with self.assertRaises(OSError):
            chassis.disable()
        self.assertEqual(chassis.state, FAULT)

    def test_non_finite_command_is_rejected_without_speed_write(self):
        self.chassis.enable_motors()
        self.bus.calls.clear()
        with self.assertRaises(ValueError):
            self.chassis.drive(float("nan"), 0.0, 0.0)
        self.assertFalse(any(call[0] == "set_speed" for call in self.bus.calls))


if __name__ == "__main__":
    unittest.main()
