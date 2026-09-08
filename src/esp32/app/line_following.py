"""Non-blocking, fail-closed line-following decisions for one rail axis.

The controller has no GPIO or scheduler side effects.  A runtime owns the
sensor reader, calls ``step`` regularly, and retains the existing chassis and
connection-health safety boundaries.
"""

import time


IDLE = "idle"
FOLLOWING = "following"
STATION = "station"
FAULT = "fault"

_ACTIVE_CHASSIS_STATES = ("enabled_stopped", "moving")
_MAX_LINEAR_SPEED_M_S = 0.60
_MAX_OMEGA_RAD_S = 0.80
_SENSOR_KEYS = (
    "line_left",
    "line_right",
    "station_left",
    "station_right",
)


def _clock_ms():
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    if hasattr(time, "monotonic"):
        return int(time.monotonic() * 1000)
    return int(time.time() * 1000)


def _ticks_diff(left, right):
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(left, right)
    return left - right


def _finite_float(value, name):
    if isinstance(value, bool):
        raise ValueError("%s must be a finite number" % name)
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError("%s must be a finite number" % name)
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError("%s must be a finite number" % name)
    return value


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("%s must be a positive integer" % name)
    return value


class LineFollowConfig:
    """Validated tuning whose polarity and steering sign are never inferred."""

    def __init__(
        self,
        active_level,
        steering_sign,
        center_pattern,
        forward_speed_m_s=0.08,
        correction_speed_m_s=0.05,
        correction_omega_rad_s=0.15,
        station_confirm_ms=120,
        line_loss_timeout_ms=150,
        max_step_gap_ms=100,
    ):
        if active_level not in (0, 1) or isinstance(active_level, bool):
            raise ValueError("active_level must be integer 0 or 1")
        if steering_sign not in (-1, 1) or isinstance(steering_sign, bool):
            raise ValueError("steering_sign must be integer -1 or 1")
        if center_pattern not in ("both_active", "both_inactive"):
            raise ValueError(
                "center_pattern must be both_active or both_inactive"
            )

        self.active_level = active_level
        self.steering_sign = steering_sign
        self.center_pattern = center_pattern
        self.forward_speed_m_s = _finite_float(
            forward_speed_m_s, "forward_speed_m_s"
        )
        self.correction_speed_m_s = _finite_float(
            correction_speed_m_s, "correction_speed_m_s"
        )
        self.correction_omega_rad_s = _finite_float(
            correction_omega_rad_s, "correction_omega_rad_s"
        )
        self.station_confirm_ms = _positive_int(
            station_confirm_ms, "station_confirm_ms"
        )
        self.line_loss_timeout_ms = _positive_int(
            line_loss_timeout_ms, "line_loss_timeout_ms"
        )
        self.max_step_gap_ms = _positive_int(max_step_gap_ms, "max_step_gap_ms")

        if not 0.0 < self.forward_speed_m_s <= _MAX_LINEAR_SPEED_M_S:
            raise ValueError("forward_speed_m_s is outside the chassis envelope")
        if not 0.0 < self.correction_speed_m_s <= self.forward_speed_m_s:
            raise ValueError(
                "correction_speed_m_s must be positive and no greater than forward speed"
            )
        if not 0.0 < self.correction_omega_rad_s <= _MAX_OMEGA_RAD_S:
            raise ValueError(
                "correction_omega_rad_s is outside the chassis envelope"
            )

    def snapshot(self):
        return {
            "active_level": self.active_level,
            "steering_sign": self.steering_sign,
            "center_pattern": self.center_pattern,
            "forward_speed_m_s": self.forward_speed_m_s,
            "correction_speed_m_s": self.correction_speed_m_s,
            "correction_omega_rad_s": self.correction_omega_rad_s,
            "station_confirm_ms": self.station_confirm_ms,
            "line_loss_timeout_ms": self.line_loss_timeout_ms,
            "max_step_gap_ms": self.max_step_gap_ms,
        }


class LineFollower:
    """Turn four digital samples into bounded calls on a chassis safety core."""

    def __init__(self, chassis, sensor_reader, config, clock_ms=None):
        if not callable(sensor_reader):
            raise ValueError("sensor_reader must be callable")
        if not isinstance(config, LineFollowConfig):
            raise ValueError("config must be LineFollowConfig")
        self.chassis = chassis
        self.sensor_reader = sensor_reader
        self.config = config
        self._clock_ms = clock_ms or _clock_ms
        self.state = IDLE
        self.reason = "not_started"
        self.direction = None
        self.last_step_ms = None
        self.last_raw = None
        self.last_active = None
        self.last_command = None
        self._line_missing_since_ms = None
        self._station_since_ms = None

    def _now(self, now_ms):
        value = self._clock_ms() if now_ms is None else now_ms
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("now_ms must be an integer")
        return value

    def _safe_stop(self):
        self.last_command = {"vx": 0.0, "vy": 0.0, "omega": 0.0}
        try:
            self.chassis.stop()
            return True
        except Exception as error:
            self.reason = "stop_failed:%s" % type(error).__name__
            return False

    def _fault(self, reason):
        stopped = self._safe_stop()
        self.state = FAULT
        if stopped:
            self.reason = reason
        return self.status_snapshot()

    def _read_active(self):
        raw = self.sensor_reader()
        if not isinstance(raw, dict):
            raise ValueError("sensor_reader must return a dict")
        normalized = {}
        active = {}
        for key in _SENSOR_KEYS:
            if key not in raw:
                raise ValueError("missing sensor %s" % key)
            value = raw[key]
            if value not in (0, 1) or isinstance(value, bool):
                raise ValueError("sensor %s must be integer 0 or 1" % key)
            normalized[key] = value
            active[key] = value == self.config.active_level
        self.last_raw = normalized
        self.last_active = active
        return active

    def start(self, direction):
        """Arm the controller without moving; the first valid step may drive."""
        if direction not in (-1, 1) or isinstance(direction, bool):
            raise ValueError("direction must be integer -1 or 1")
        if self.state not in (IDLE, STATION):
            raise RuntimeError("line follower must be idle or at a station")
        if getattr(self.chassis, "state", None) != "enabled_stopped":
            raise RuntimeError("chassis must be enabled_stopped")
        if not self._safe_stop():
            self.state = FAULT
            return self.status_snapshot()

        self.state = FOLLOWING
        self.reason = "awaiting_sensor_sample"
        self.direction = direction
        self.last_step_ms = None
        self.last_raw = None
        self.last_active = None
        self._line_missing_since_ms = None
        self._station_since_ms = None
        return self.status_snapshot()

    def step(self, now_ms=None):
        """Perform one decision; callers must invoke this within max_step_gap_ms."""
        if self.state != FOLLOWING:
            return self.status_snapshot()
        try:
            now_ms = self._now(now_ms)
        except ValueError:
            return self._fault("invalid_clock")

        if self.last_step_ms is not None:
            elapsed = _ticks_diff(now_ms, self.last_step_ms)
            if elapsed < 0:
                return self._fault("clock_moved_backwards")
            if elapsed > self.config.max_step_gap_ms:
                return self._fault("step_timeout")
        self.last_step_ms = now_ms

        if getattr(self.chassis, "state", None) not in _ACTIVE_CHASSIS_STATES:
            return self._fault("chassis_not_active")

        try:
            active = self._read_active()
        except Exception as error:
            return self._fault("sensor_invalid:%s" % type(error).__name__)

        station_candidate = active["station_left"] and active["station_right"]
        if station_candidate:
            if not self._safe_stop():
                self.state = FAULT
                return self.status_snapshot()
            if self._station_since_ms is None:
                self._station_since_ms = now_ms
            self._line_missing_since_ms = None
            if (
                _ticks_diff(now_ms, self._station_since_ms)
                >= self.config.station_confirm_ms
            ):
                self.state = STATION
                self.reason = "station_confirmed"
            else:
                self.reason = "station_candidate"
            return self.status_snapshot()

        self._station_since_ms = None
        line_left = active["line_left"]
        line_right = active["line_right"]
        equal_pattern = line_left == line_right
        centered = equal_pattern and (
            (line_left and self.config.center_pattern == "both_active")
            or (not line_left and self.config.center_pattern == "both_inactive")
        )
        line_missing = equal_pattern and not centered
        if line_missing:
            if not self._safe_stop():
                self.state = FAULT
                return self.status_snapshot()
            if self._line_missing_since_ms is None:
                self._line_missing_since_ms = now_ms
            if (
                _ticks_diff(now_ms, self._line_missing_since_ms)
                >= self.config.line_loss_timeout_ms
            ):
                self.state = FAULT
                self.reason = "line_lost"
            else:
                self.reason = "line_missing"
            return self.status_snapshot()

        self._line_missing_since_ms = None
        vx = self.direction * self.config.forward_speed_m_s
        omega = 0.0
        if not centered:
            vx = self.direction * self.config.correction_speed_m_s
            omega = self.config.correction_omega_rad_s
            if line_right:
                omega = -omega
            omega *= self.config.steering_sign

        try:
            self.chassis.drive(vx, 0.0, omega)
        except Exception as error:
            return self._fault("drive_failed:%s" % type(error).__name__)
        self.last_command = {"vx": vx, "vy": 0.0, "omega": omega}
        self.reason = "centered" if omega == 0.0 else "correcting"
        return self.status_snapshot()

    def stop(self, reason="requested"):
        """Stop without disabling so the owning runtime can choose the next state."""
        if not isinstance(reason, str) or not reason:
            raise ValueError("reason must be a non-empty string")
        if not self._safe_stop():
            self.state = FAULT
            return self.status_snapshot()
        if self.state == FAULT:
            return self.status_snapshot()
        self.state = IDLE
        self.reason = reason
        self.direction = None
        self._line_missing_since_ms = None
        self._station_since_ms = None
        return self.status_snapshot()

    def reset_fault(self):
        """Clear only this layer after the chassis is independently stopped."""
        if self.state != FAULT:
            raise RuntimeError("line follower is not faulted")
        if getattr(self.chassis, "state", None) != "enabled_stopped":
            raise RuntimeError("chassis must be enabled_stopped")
        self.state = IDLE
        self.reason = "fault_reset"
        self.direction = None
        self.last_step_ms = None
        self._line_missing_since_ms = None
        self._station_since_ms = None
        return self.status_snapshot()

    def status_snapshot(self):
        return {
            "state": self.state,
            "reason": self.reason,
            "direction": self.direction,
            "last_step_ms": self.last_step_ms,
            "sensors_raw": None if self.last_raw is None else dict(self.last_raw),
            "sensors_active": (
                None if self.last_active is None else dict(self.last_active)
            ),
            "last_command": (
                None if self.last_command is None else dict(self.last_command)
            ),
            "config": self.config.snapshot(),
        }
