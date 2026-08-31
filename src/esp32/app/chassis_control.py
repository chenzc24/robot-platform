"""Hardware-independent safe state machine for the mecanum chassis."""

import math


DISABLED = "disabled"
ENABLING = "enabling"
ENABLED_STOPPED = "enabled_stopped"
MOVING = "moving"
FAULT = "fault"

MAX_CHASSIS_LINEAR_SPEED_M_S = 0.60
MAX_CHASSIS_OMEGA_RAD_S = 0.80
DEFAULT_ACC_RAD_S2 = 20.0
MAX_MOTOR_RPM = 200.0
MECANUM_LX_M = 0.41 / 2
MECANUM_LY_M = 0.41 / 2
WHEEL_RADIUS_M = 0.0635

_MAX_MOTOR_RAD_S = MAX_MOTOR_RPM * 2.0 * math.pi / 60.0
_STOP_EPS_RAD_S = 0.01
_DRIVE_WHEELS = (
    (1, -1),
    (2, 1),
    (3, -1),
    (4, 1),
)


class ChassisStateError(RuntimeError):
    """Raised when a command is unsafe for the current chassis state."""


def _finite_float(value, name):
    value = float(value)
    if value != value or value in (float("inf"), -float("inf")):
        raise ValueError("%s must be finite" % name)
    return value


def _clamp(value, low, high):
    return max(low, min(high, value))


class SafeMecanumChassis:
    """Enforce explicit enable, zero-target, stop, disable, and fault rules.

    The injected motor bus must provide ``prepare_speed_mode``, ``set_acc``,
    ``set_speed``, ``stop_all``, and ``disable_all``. This class deliberately
    does not claim that a sent command was acknowledged by real hardware.
    """

    def __init__(self, motor_bus):
        self.motor_bus = motor_bus
        self.motor_ids = tuple(item[0] for item in _DRIVE_WHEELS)
        self.state = DISABLED
        self.last_wheel_speeds = (0.0, 0.0, 0.0, 0.0)
        self.last_error = None

    def _best_effort_safe_output(self):
        try:
            self.motor_bus.stop_all(self.motor_ids)
        except Exception:
            pass
        try:
            self.motor_bus.disable_all(self.motor_ids)
        except Exception:
            pass
        self.last_wheel_speeds = (0.0, 0.0, 0.0, 0.0)

    def _fault(self, error):
        self.last_error = error
        self.state = FAULT
        self._best_effort_safe_output()

    def status_snapshot(self):
        """Return hardware-independent state for telemetry and diagnostics."""
        error = None
        if self.last_error is not None:
            error = {
                "type": type(self.last_error).__name__,
                "message": str(self.last_error),
            }
        return {
            "state": self.state,
            "motor_ids": self.motor_ids,
            "wheel_speeds_rad_s": self.last_wheel_speeds,
            "last_error": error,
        }

    def enable_motors(self):
        """Enable only from DISABLED, with explicit zero targets around setup."""
        if self.state != DISABLED:
            raise ChassisStateError("enable requires DISABLED state")

        self.state = ENABLING
        try:
            self.motor_bus.disable_all(self.motor_ids)
            self.motor_bus.stop_all(self.motor_ids)
            self.motor_bus.prepare_speed_mode(self.motor_ids)
            self.motor_bus.stop_all(self.motor_ids)
        except Exception as error:
            self._fault(error)
            raise

        self.last_error = None
        self.last_wheel_speeds = (0.0, 0.0, 0.0, 0.0)
        self.state = ENABLED_STOPPED

    def stop(self):
        """Always send a zero target; never skip a stop because of cached state."""
        previous_state = self.state
        try:
            self.motor_bus.stop_all(self.motor_ids)
        except Exception as error:
            self._fault(error)
            raise

        self.last_wheel_speeds = (0.0, 0.0, 0.0, 0.0)
        if previous_state in (ENABLED_STOPPED, MOVING):
            self.state = ENABLED_STOPPED

    def disable(self):
        """Send zero then disable every motor; any failure leaves FAULT state."""
        first_error = None
        try:
            self.motor_bus.stop_all(self.motor_ids)
        except Exception as error:
            first_error = error
        try:
            self.motor_bus.disable_all(self.motor_ids)
        except Exception as error:
            if first_error is None:
                first_error = error

        self.last_wheel_speeds = (0.0, 0.0, 0.0, 0.0)
        if first_error is not None:
            self.last_error = first_error
            self.state = FAULT
            raise first_error

        self.last_error = None
        self.state = DISABLED

    def drive_wheel_speeds(
        self,
        left_front,
        right_front,
        left_rear,
        right_rear,
        acc_rad_s2=DEFAULT_ACC_RAD_S2,
    ):
        """Write bounded wheel targets only while explicitly enabled."""
        if self.state not in (ENABLED_STOPPED, MOVING):
            raise ChassisStateError("drive requires an enabled chassis")

        values = (
            _finite_float(left_front, "left_front"),
            _finite_float(right_front, "right_front"),
            _finite_float(left_rear, "left_rear"),
            _finite_float(right_rear, "right_rear"),
        )
        acc_rad_s2 = _finite_float(acc_rad_s2, "acc_rad_s2")
        if acc_rad_s2 <= 0:
            raise ValueError("acc_rad_s2 must be positive")

        max_abs = max(abs(value) for value in values)
        if max_abs > _MAX_MOTOR_RAD_S:
            scale = _MAX_MOTOR_RAD_S / max_abs
            values = tuple(value * scale for value in values)

        if max(abs(value) for value in values) < _STOP_EPS_RAD_S:
            self.stop()
            return self.last_wheel_speeds

        try:
            for (motor_id, direction), wheel_speed in zip(_DRIVE_WHEELS, values):
                self.motor_bus.set_acc(motor_id, acc_rad_s2)
                self.motor_bus.set_speed(motor_id, wheel_speed * direction)
        except Exception as error:
            self._fault(error)
            raise

        self.last_wheel_speeds = values
        self.state = MOVING
        return values

    def drive(self, vx, vy, omega, acc_rad_s2=DEFAULT_ACC_RAD_S2):
        """Convert bounded chassis velocity to four wheel angular velocities."""
        vx = _finite_float(vx, "vx")
        vy = _finite_float(vy, "vy")
        omega = _finite_float(omega, "omega")

        linear_speed = math.sqrt(vx * vx + vy * vy)
        if linear_speed > MAX_CHASSIS_LINEAR_SPEED_M_S:
            scale = MAX_CHASSIS_LINEAR_SPEED_M_S / linear_speed
            vx *= scale
            vy *= scale
        omega = _clamp(omega, -MAX_CHASSIS_OMEGA_RAD_S, MAX_CHASSIS_OMEGA_RAD_S)

        k = MECANUM_LX_M + MECANUM_LY_M
        wheel_speeds = (
            (vx - vy - k * omega) / WHEEL_RADIUS_M,
            (vx + vy + k * omega) / WHEEL_RADIUS_M,
            (vx + vy - k * omega) / WHEEL_RADIUS_M,
            (vx - vy + k * omega) / WHEEL_RADIUS_M,
        )
        return self.drive_wheel_speeds(*wheel_speeds, acc_rad_s2=acc_rad_s2)
