"""Hardware-independent exclusive control lease for remote command owners."""

import time


MIN_TIMEOUT_MS = 100
MAX_TIMEOUT_MS = 10_000


def _clock_ms():
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    if hasattr(time, "monotonic"):
        return int(time.monotonic() * 1000)
    return int(time.time() * 1000)


def _ticks_add(value, delta):
    if hasattr(time, "ticks_add"):
        return time.ticks_add(value, delta)
    return value + delta


def _ticks_diff(left, right):
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(left, right)
    return left - right


class ControlLeaseError(RuntimeError):
    """Raised when a caller violates exclusive control ownership."""


class ControlLease:
    """Track one bounded control owner without touching motion hardware.

    Expiration only clears ownership. A future chassis service must react to an
    expired owner by issuing its own local stop and disable sequence.
    """

    def __init__(self, clock_ms=None):
        self._clock_ms = clock_ms or _clock_ms
        self.owner = None
        self.deadline_ms = None

    @staticmethod
    def _validate_owner(owner):
        if not isinstance(owner, str) or not owner.strip():
            raise ValueError("owner must be a non-empty string")
        return owner.strip()

    @staticmethod
    def _validate_timeout(timeout_ms):
        if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int):
            raise ValueError("timeout_ms must be an integer")
        if not MIN_TIMEOUT_MS <= timeout_ms <= MAX_TIMEOUT_MS:
            raise ValueError(
                "timeout_ms must be in %d..%d" % (MIN_TIMEOUT_MS, MAX_TIMEOUT_MS)
            )
        return timeout_ms

    def _is_expired_at(self, now_ms):
        return self.owner is not None and _ticks_diff(now_ms, self.deadline_ms) >= 0

    def expire_if_needed(self):
        now_ms = self._clock_ms()
        if not self._is_expired_at(now_ms):
            return None
        expired_owner = self.owner
        self.owner = None
        self.deadline_ms = None
        return expired_owner

    def acquire(self, owner, timeout_ms):
        owner = self._validate_owner(owner)
        timeout_ms = self._validate_timeout(timeout_ms)
        self.expire_if_needed()
        if self.owner is not None and self.owner != owner:
            raise ControlLeaseError("control is owned by %s" % self.owner)
        now_ms = self._clock_ms()
        self.owner = owner
        self.deadline_ms = _ticks_add(now_ms, timeout_ms)
        return self.status()

    def renew(self, owner, timeout_ms):
        owner = self._validate_owner(owner)
        timeout_ms = self._validate_timeout(timeout_ms)
        expired_owner = self.expire_if_needed()
        if expired_owner is not None:
            raise ControlLeaseError("control lease expired")
        if self.owner != owner:
            raise ControlLeaseError("control lease is not owned by %s" % owner)
        now_ms = self._clock_ms()
        self.deadline_ms = _ticks_add(now_ms, timeout_ms)
        return self.status()

    def release(self, owner):
        owner = self._validate_owner(owner)
        if self.owner != owner:
            raise ControlLeaseError("control lease is not owned by %s" % owner)
        self.owner = None
        self.deadline_ms = None
        return self.status()

    def status(self):
        self.expire_if_needed()
        remaining_ms = 0
        if self.owner is not None:
            remaining_ms = max(0, _ticks_diff(self.deadline_ms, self._clock_ms()))
        return {
            "owner": self.owner,
            "active": self.owner is not None,
            "remaining_ms": remaining_ms,
        }
