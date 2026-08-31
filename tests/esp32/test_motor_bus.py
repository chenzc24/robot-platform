"""CAN frame and rollback tests for the formal ESP32 MotorBus adapter."""

import pathlib
import struct
import sys
import unittest


APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "esp32" / "app"
sys.path.insert(0, str(APP_DIR))

from chassis_control import ENABLED_STOPPED, SafeMecanumChassis
from motor_bus import (
    COMM_DISABLE,
    COMM_ENABLE,
    COMM_WRITE_PARAM,
    PARAM_MODE,
    PARAM_SPEED,
    MotorBus,
    build_ext_id,
)


class FakeCan:
    def __init__(self, fail_calls=(), false_calls=()):
        self.calls = []
        self.fail_calls = set(fail_calls)
        self.false_calls = set(false_calls)

    def send(self, payload, ext_id, extframe=False):
        call_number = len(self.calls) + 1
        self.calls.append((tuple(payload), ext_id, extframe))
        if call_number in self.fail_calls:
            raise OSError("injected CAN failure %d" % call_number)
        if call_number in self.false_calls:
            return False
        return None


def comm_type(frame):
    return (frame[1] >> 24) & 0x1F


def motor_id(frame):
    return frame[1] & 0xFF


def param_index(frame):
    return struct.unpack("<H", bytes(frame[0][:2]))[0]


def param_float(frame):
    return struct.unpack("<f", bytes(frame[0][4:8]))[0]


def is_zero_speed_frame(frame):
    return (
        comm_type(frame) == COMM_WRITE_PARAM
        and param_index(frame) == PARAM_SPEED
        and param_float(frame) == 0.0
    )


class FrameEncodingTests(unittest.TestCase):
    def test_extended_id_vector(self):
        self.assertEqual(build_ext_id(COMM_WRITE_PARAM, 1, 0x00FD), 0x1200FD01)

    def test_speed_mode_uint32_frame_vector(self):
        can = FakeCan()
        MotorBus(can, sleep_ms=lambda _ms: None).set_speed_mode(1)
        self.assertEqual(len(can.calls), 1)
        payload, ext_id, extframe = can.calls[0]
        self.assertEqual(ext_id, 0x1200FD01)
        self.assertTrue(extframe)
        self.assertEqual(payload, (0x05, 0x70, 0, 0, 2, 0, 0, 0))

    def test_speed_float_is_little_endian_and_driver_limited(self):
        can = FakeCan()
        MotorBus(can, sleep_ms=lambda _ms: None).set_speed(2, 100.0)
        frame = can.calls[0]
        self.assertEqual(comm_type(frame), COMM_WRITE_PARAM)
        self.assertEqual(motor_id(frame), 2)
        self.assertEqual(param_index(frame), PARAM_SPEED)
        self.assertAlmostEqual(param_float(frame), 44.0)

    def test_invalid_id_payload_and_non_finite_speed_are_rejected(self):
        bus = MotorBus(FakeCan(), sleep_ms=lambda _ms: None)
        with self.assertRaises(ValueError):
            build_ext_id(COMM_WRITE_PARAM, 256, 0x00FD)
        with self.assertRaises(ValueError):
            build_ext_id(COMM_WRITE_PARAM, 1.5, 0x00FD)
        with self.assertRaises(ValueError):
            bus._send(1, COMM_ENABLE, [0] * 7)
        with self.assertRaises(ValueError):
            bus.set_speed(1, float("nan"))

    def test_false_can_result_is_a_send_failure(self):
        bus = MotorBus(FakeCan(false_calls=(1,)), sleep_ms=lambda _ms: None)
        with self.assertRaises(OSError):
            bus.stop(1)


class SafetySequenceTests(unittest.TestCase):
    def test_single_motor_enable_has_zero_target_on_both_sides(self):
        can = FakeCan()
        MotorBus(can, sleep_ms=lambda _ms: None).init_speed_mode(1)
        enable_index = next(
            index for index, frame in enumerate(can.calls) if comm_type(frame) == COMM_ENABLE
        )
        self.assertTrue(is_zero_speed_frame(can.calls[enable_index - 1]))
        self.assertTrue(is_zero_speed_frame(can.calls[enable_index + 1]))

    def test_stop_all_attempts_every_motor_after_one_send_failure(self):
        can = FakeCan(fail_calls=(2,))
        bus = MotorBus(can, sleep_ms=lambda _ms: None)
        with self.assertRaises(OSError):
            bus.stop_all((1, 2, 3, 4))
        self.assertEqual([motor_id(frame) for frame in can.calls], [1, 2, 3, 4])

    def test_disable_all_continues_to_disable_after_stop_failure(self):
        can = FakeCan(fail_calls=(2,))
        bus = MotorBus(can, sleep_ms=lambda _ms: None)
        with self.assertRaises(OSError):
            bus.disable_all((1, 2, 3, 4))
        disable_frames = [frame for frame in can.calls if comm_type(frame) == COMM_DISABLE]
        self.assertEqual([motor_id(frame) for frame in disable_frames], [1, 2, 3, 4])

    def test_prepare_failure_rolls_back_every_motor(self):
        can = FakeCan(fail_calls=(11,))
        bus = MotorBus(can, sleep_ms=lambda _ms: None)
        with self.assertRaises(OSError):
            bus.prepare_speed_mode((1, 2, 3, 4))
        rollback_disable_frames = [
            frame for frame in can.calls[11:] if comm_type(frame) == COMM_DISABLE
        ]
        self.assertEqual(
            [motor_id(frame) for frame in rollback_disable_frames],
            [1, 2, 3, 4],
        )

    def test_safe_chassis_and_real_adapter_reach_enabled_stopped(self):
        can = FakeCan()
        bus = MotorBus(can, sleep_ms=lambda _ms: None)
        chassis = SafeMecanumChassis(bus)
        chassis.enable_motors()
        self.assertEqual(chassis.state, ENABLED_STOPPED)
        self.assertTrue(all(is_zero_speed_frame(frame) for frame in can.calls[-4:]))


if __name__ == "__main__":
    unittest.main()
