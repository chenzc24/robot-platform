"""Tests for opt-in GPIO construction of the ESP32 line follower."""

import pathlib
import sys
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/esp32/app"))

from line_follow_runtime import create_line_follower


class Chassis:
    state = "enabled_stopped"

    def stop(self):
        self.state = "enabled_stopped"

    def drive(self, _vx, _vy, _omega):
        self.state = "moving"


def config(**overrides):
    values = {
        "LINE_FOLLOW_ENABLED": True,
        "LINE_FOLLOW_LEFT_PIN": 1,
        "LINE_FOLLOW_RIGHT_PIN": 2,
        "LINE_FOLLOW_STATION_LEFT_PIN": 3,
        "LINE_FOLLOW_STATION_RIGHT_PIN": 4,
        "LINE_FOLLOW_PIN_PULL": "up",
        "LINE_FOLLOW_ACTIVE_LEVEL": 0,
        "LINE_FOLLOW_STEERING_SIGN": 1,
        "LINE_FOLLOW_CENTER_PATTERN": "both_active",
        "LINE_FOLLOW_FORWARD_SPEED_M_S": 0.08,
        "LINE_FOLLOW_CORRECTION_SPEED_M_S": 0.05,
        "LINE_FOLLOW_CORRECTION_OMEGA_RAD_S": 0.15,
        "LINE_FOLLOW_STATION_CONFIRM_MS": 120,
        "LINE_FOLLOW_LINE_LOSS_TIMEOUT_MS": 150,
        "LINE_FOLLOW_MAX_STEP_GAP_MS": 100,
    }
    values.update(overrides)
    return types.SimpleNamespace(**values)


class Pin:
    def __init__(self, number, _pull):
        self.number = number

    def value(self):
        return 0 if self.number in (1, 2) else 1


class LineFollowRuntimeTests(unittest.TestCase):
    def test_disabled_mode_constructs_no_gpio(self):
        calls = []
        follower = create_line_follower(
            types.SimpleNamespace(LINE_FOLLOW_ENABLED=False),
            Chassis(),
            pin_factory=lambda *_args: calls.append(_args),
        )
        self.assertIsNone(follower)
        self.assertEqual(calls, [])

    def test_enabled_mode_reads_four_explicit_pins(self):
        calls = []

        def factory(number, pull):
            calls.append((number, pull))
            return Pin(number, pull)

        follower = create_line_follower(config(), Chassis(), pin_factory=factory)
        follower.start(1)
        result = follower.step(1000)
        self.assertEqual(result["state"], "following")
        self.assertEqual(result["reason"], "centered")
        self.assertEqual(calls, [(1, "up"), (2, "up"), (3, "up"), (4, "up")])

    def test_duplicate_or_missing_pins_reject_before_gpio(self):
        calls = []
        for candidate in (
            config(LINE_FOLLOW_RIGHT_PIN=1),
            config(LINE_FOLLOW_LEFT_PIN=None),
        ):
            with self.subTest(candidate=candidate), self.assertRaises(RuntimeError):
                create_line_follower(
                    candidate,
                    Chassis(),
                    pin_factory=lambda *_args: calls.append(_args),
                )
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
