"""Validated CAN adapter for the chassis motor speed-mode protocol."""

import time

try:
    import ustruct as struct
except ImportError:
    import struct


HOST_ID = 0x00FD
DRIVER_SPEED_LIMIT_RAD_S = 44.0
DEFAULT_ACC_RAD_S2 = 20.0
MOTOR_SPEED_PI_KP = 5.0
MOTOR_SPEED_PI_KI = 0.02
MOTOR_SPEED_FILTER_GAIN = 0.1

COMM_ENABLE = 0x03
COMM_DISABLE = 0x04
COMM_WRITE_PARAM = 0x12

PARAM_MODE = 0x7005
PARAM_SPEED = 0x700A
PARAM_SPEED_PI_KP = 0x701F
PARAM_SPEED_PI_KI = 0x7020
PARAM_SPEED_FILTER_GAIN = 0x7021
PARAM_ACCELERATION = 0x7022
MODE_SPEED = 2


def _finite_float(value, name):
    value = float(value)
    if value != value or value in (float("inf"), -float("inf")):
        raise ValueError("%s must be finite" % name)
    return value


def _bounded_int(value, low, high, name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("%s must be an integer" % name)
    if value < low or value > high:
        raise ValueError("%s must be in %d..%d" % (name, low, high))
    return value


def _default_sleep_ms(milliseconds):
    milliseconds = int(milliseconds)
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(milliseconds)
    else:
        time.sleep(milliseconds / 1000.0)


def build_ext_id(comm_type, motor_id, data2=0):
    """Build the protocol's 29-bit extended CAN identifier."""
    comm_type = _bounded_int(comm_type, 0, 0x1F, "comm_type")
    motor_id = _bounded_int(motor_id, 0, 0xFF, "motor_id")
    data2 = _bounded_int(data2, 0, 0xFFFF, "data2")
    return (comm_type << 24) | (data2 << 8) | motor_id


class MotorBus:
    """Send validated motor commands through an injected MicroPython CAN API."""

    def __init__(self, can_bus, sleep_ms=None):
        if can_bus is None:
            raise ValueError("can_bus is required")
        self.can = can_bus
        self._sleep_ms = sleep_ms or _default_sleep_ms

    @staticmethod
    def _motor_id(motor_id):
        return _bounded_int(motor_id, 1, 0xFF, "motor_id")

    @staticmethod
    def _motor_ids(motor_ids):
        result = tuple(MotorBus._motor_id(motor_id) for motor_id in motor_ids)
        if not result:
            raise ValueError("motor_ids must not be empty")
        if len(set(result)) != len(result):
            raise ValueError("motor_ids must be unique")
        return result

    def _send(self, motor_id, comm_type, data, data2=HOST_ID):
        motor_id = self._motor_id(motor_id)
        payload = list(data)
        if len(payload) != 8:
            raise ValueError("CAN payload must contain exactly 8 bytes")
        payload = [_bounded_int(value, 0, 0xFF, "payload byte") for value in payload]
        ext_id = build_ext_id(comm_type, motor_id, data2)
        result = self.can.send(payload, ext_id, extframe=True)
        if result is False:
            raise OSError("CAN send returned False")
        return result

    def write_param_uint32(self, motor_id, index, value):
        index = _bounded_int(index, 0, 0xFFFF, "parameter index")
        value = _bounded_int(value, 0, 0xFFFFFFFF, "uint32 value")
        data = list(struct.pack("<H", index)) + [0x00, 0x00]
        data += list(struct.pack("<I", value))
        return self._send(motor_id, COMM_WRITE_PARAM, data)

    def write_param_float(self, motor_id, index, value):
        index = _bounded_int(index, 0, 0xFFFF, "parameter index")
        value = _finite_float(value, "float value")
        data = list(struct.pack("<H", index)) + [0x00, 0x00]
        data += list(struct.pack("<f", value))
        return self._send(motor_id, COMM_WRITE_PARAM, data)

    def set_speed_mode(self, motor_id):
        return self.write_param_uint32(motor_id, PARAM_MODE, MODE_SPEED)

    def set_acc(self, motor_id, acc_rad_s2=DEFAULT_ACC_RAD_S2):
        acc_rad_s2 = _finite_float(acc_rad_s2, "acc_rad_s2")
        if acc_rad_s2 <= 0:
            raise ValueError("acc_rad_s2 must be positive")
        return self.write_param_float(motor_id, PARAM_ACCELERATION, acc_rad_s2)

    def set_speed_filter_gain(self, motor_id, gain=MOTOR_SPEED_FILTER_GAIN):
        gain = _finite_float(gain, "speed filter gain")
        if gain < 0 or gain > 1:
            raise ValueError("speed filter gain must be in 0..1")
        return self.write_param_float(motor_id, PARAM_SPEED_FILTER_GAIN, gain)

    def set_speed_pi(self, motor_id, kp=MOTOR_SPEED_PI_KP, ki=MOTOR_SPEED_PI_KI):
        kp = _finite_float(kp, "speed PI kp")
        ki = _finite_float(ki, "speed PI ki")
        if kp < 0 or ki < 0:
            raise ValueError("speed PI gains must not be negative")
        self.write_param_float(motor_id, PARAM_SPEED_PI_KP, kp)
        self._sleep_ms(20)
        return self.write_param_float(motor_id, PARAM_SPEED_PI_KI, ki)

    def enable_only(self, motor_id):
        return self._send(motor_id, COMM_ENABLE, [0] * 8)

    def disable(self, motor_id):
        return self._send(motor_id, COMM_DISABLE, [0] * 8)

    def clear_fault(self, motor_id):
        return self._send(motor_id, COMM_DISABLE, [1] + [0] * 7)

    def set_speed(self, motor_id, speed_rad_s):
        speed_rad_s = _finite_float(speed_rad_s, "speed_rad_s")
        speed_rad_s = max(
            -DRIVER_SPEED_LIMIT_RAD_S,
            min(DRIVER_SPEED_LIMIT_RAD_S, speed_rad_s),
        )
        return self.write_param_float(motor_id, PARAM_SPEED, speed_rad_s)

    def stop(self, motor_id):
        return self.set_speed(motor_id, 0.0)

    def init_speed_mode(self, motor_id, kp=MOTOR_SPEED_PI_KP, ki=MOTOR_SPEED_PI_KI):
        """Configure one motor with zero targets immediately around enable."""
        motor_id = self._motor_id(motor_id)
        self.disable(motor_id)
        self._sleep_ms(20)
        self.clear_fault(motor_id)
        self._sleep_ms(20)
        self.set_speed_mode(motor_id)
        self._sleep_ms(50)
        self.set_speed_pi(motor_id, kp, ki)
        self._sleep_ms(20)
        self.set_speed_filter_gain(motor_id)
        self._sleep_ms(20)
        self.set_acc(motor_id, DEFAULT_ACC_RAD_S2)
        self._sleep_ms(20)
        self.stop(motor_id)
        self._sleep_ms(20)
        self.enable_only(motor_id)
        self._sleep_ms(50)
        self.stop(motor_id)
        self._sleep_ms(20)

    def prepare_speed_mode(self, motor_ids):
        """Initialize every motor, rolling the full set back on any failure."""
        motor_ids = self._motor_ids(motor_ids)
        try:
            for motor_id in motor_ids:
                self.init_speed_mode(motor_id)
        except Exception:
            try:
                self.disable_all(motor_ids)
            except Exception:
                pass
            raise

    def stop_all(self, motor_ids):
        """Attempt a zero target for every motor, then raise the first error."""
        motor_ids = self._motor_ids(motor_ids)
        first_error = None
        for motor_id in motor_ids:
            try:
                self.stop(motor_id)
            except Exception as error:
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error

    def disable_all(self, motor_ids):
        """Attempt stop and disable for every motor despite individual errors."""
        motor_ids = self._motor_ids(motor_ids)
        first_error = None
        try:
            self.stop_all(motor_ids)
        except Exception as error:
            first_error = error
        for motor_id in motor_ids:
            try:
                self.disable(motor_id)
            except Exception as error:
                if first_error is None:
                    first_error = error
        if first_error is not None:
            raise first_error
