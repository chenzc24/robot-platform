"""MicroPython-compatible structured runtime status reporting."""

import time

try:
    import ujson as json
except ImportError:
    import json


SCHEMA_VERSION = 1
VALID_STATES = (
    "starting",
    "idle",
    "ready",
    "running",
    "stopping",
    "stopped",
    "disconnected",
    "safe_idle",
    "fault",
    "estop",
)


def _clock_ms():
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    if hasattr(time, "monotonic"):
        return int(time.monotonic() * 1000)
    return int(time.time() * 1000)


def _encode(payload):
    try:
        return json.dumps(payload, sort_keys=True)
    except TypeError:
        return json.dumps(payload)


def _is_token(value, allow_hyphen=False):
    if not isinstance(value, str) or not value:
        return False
    if value[0] < "a" or value[0] > "z":
        return False
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789_"
    if allow_hyphen:
        allowed += "-"
    return all(character in allowed for character in value[1:])


class RuntimeStatus:
    """Build and optionally emit events that follow the shared status schema."""

    def __init__(
        self,
        device,
        subsystem,
        initial_state="idle",
        clock_ms=None,
        output=None,
    ):
        if not _is_token(device, allow_hyphen=True):
            raise ValueError("device must be a lowercase identifier")
        if not _is_token(subsystem, allow_hyphen=True):
            raise ValueError("subsystem must be a lowercase identifier")
        self._validate_state(initial_state)
        self.device = device
        self.subsystem = subsystem
        self.state = initial_state
        self.sequence = 0
        self.error_code = None
        self.detail = {}
        self._clock_ms = clock_ms or _clock_ms
        self._output = output or print
        self._started_ms = self._clock_ms()

    @staticmethod
    def _validate_state(state):
        if state not in VALID_STATES:
            raise ValueError("unsupported runtime state: %s" % state)

    @staticmethod
    def _validate_detail(detail):
        if detail is None:
            return {}
        if not isinstance(detail, dict):
            raise ValueError("detail must be a dictionary")
        return dict(detail)

    def _uptime_ms(self):
        now = self._clock_ms()
        if hasattr(time, "ticks_diff"):
            return max(0, time.ticks_diff(now, self._started_ms))
        return max(0, now - self._started_ms)

    def snapshot(self, event="status"):
        if not _is_token(event):
            raise ValueError("event must be a lowercase identifier")
        return {
            "schema_version": SCHEMA_VERSION,
            "event": event,
            "device": self.device,
            "subsystem": self.subsystem,
            "state": self.state,
            "sequence": self.sequence,
            "uptime_ms": self._uptime_ms(),
            "error_code": self.error_code,
            "detail": dict(self.detail),
        }

    def transition(
        self,
        state,
        event="state_changed",
        error_code=None,
        detail=None,
        emit=True,
    ):
        self._validate_state(state)
        if error_code is not None and not _is_token(error_code):
            raise ValueError("error_code must be a lowercase identifier or None")
        self.state = state
        self.error_code = error_code
        self.detail = self._validate_detail(detail)
        self.sequence += 1
        payload = self.snapshot(event)
        if emit:
            self._output(_encode(payload))
        return payload
