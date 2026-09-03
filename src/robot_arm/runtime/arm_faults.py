"""Bounded fault evidence and explicit, capability-gated recovery.

Controller callbacks consume/return normalized values from a separately verified
vendor adapter. The current DobotStudio project deliberately supplies none.
"""

import json

from motion_link import encode_fields, FAULT_FIELDS


RAW_BYTES = 64


def safe_token(value, fallback="execution_failed"):
    value = str(value)
    if not value or len(value) > 64 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789" for c in value):
        return fallback
    return value


def raw_evidence(value):
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        text = repr(value)
    data = text.encode("utf-8", errors="replace")
    return data[:RAW_BYTES].hex(), int(len(data) > RAW_BYTES)


class ArmFault(ValueError):
    def __init__(self, code, category="service", vendor_api="none", vendor_code=None, raw=None):
        ValueError.__init__(self, code)
        self.code, self.category = safe_token(code), safe_token(category)[:16]
        self.vendor_api = safe_token(vendor_api, "unknown")[:32]
        self.vendor_code = vendor_code if type(vendor_code) is int and -2147483648 <= vendor_code <= 2147483647 else None
        self.raw = raw


def fault_record(error, clock_ms, fault_id):
    raw_hex, truncated = raw_evidence(error.raw if isinstance(error, ArmFault) else str(error))
    return dict(zip(FAULT_FIELDS, (
        safe_token(getattr(error, "code", str(error))), 0,
        getattr(error, "category", "service"),
        getattr(error, "vendor_code", None) if getattr(error, "vendor_code", None) is not None else "unknown",
        getattr(error, "vendor_api", "none"), raw_hex, truncated, clock_ms(), fault_id,
    )))


def fault_payload(record):
    return encode_fields((key, record[key]) for key in FAULT_FIELDS)


class ControllerFaultAccess:
    """No socket creation, automatic capability discovery, or motion operations.

read() must return a fresh dict containing alarm_codes (list of integer vendor
codes), stationary, queue_empty and emergency_stop (strict bools). clear()
must return a verified integer vendor result; zero only means request success.
"""

    def __init__(self, read=None, clear=None):
        if read is not None and not callable(read) or clear is not None and not callable(clear):
            raise ValueError("invalid_fault_adapter")
        self.read, self.clear = read, clear
        self.audit = []

    def _remember(self, action, value, clock_ms):
        raw_hex, truncated = raw_evidence(value)
        self.audit.append({"action": action, "raw_hex": raw_hex, "raw_truncated": truncated, "sample_time_ms": clock_ms()})
        self.audit[:] = self.audit[-16:]

    def snapshot(self, clock_ms):
        if self.read is None:
            raise ArmFault("controller_query_unsupported", "capability")
        try:
            state = self.read()
        except Exception as error:
            raise ArmFault("controller_query_failed", "controller", "fault_query", raw=str(error))
        self._remember("query", state, clock_ms)
        required = {"alarm_codes", "stationary", "queue_empty", "emergency_stop"}
        if (not isinstance(state, dict) or set(state) != required
                or not isinstance(state["alarm_codes"], list)
                or any(type(code) is not int or not -2147483648 <= code <= 2147483647 for code in state["alarm_codes"])
                or len(state["alarm_codes"]) > 32
                or any(type(state[key]) is not bool for key in required - {"alarm_codes"})):
            raise ArmFault("controller_state_unverified", "controller", "fault_query", raw=state)
        return dict(state, alarm_codes=list(state["alarm_codes"]), sample_time_ms=clock_ms())

    @staticmethod
    def _safe(state):
        if not state["stationary"] or not state["queue_empty"] or state["emergency_stop"]:
            raise ArmFault("controller_recovery_unsafe", "recovery", raw=state)

    def clear_alarms(self, clock_ms):
        if self.read is None or self.clear is None:
            raise ArmFault("controller_clear_unsupported", "capability")
        before = self.snapshot(clock_ms)
        self._safe(before)
        try:
            result = self.clear()
        except Exception as error:
            raise ArmFault("controller_clear_unconfirmed", "recovery", "ClearError", raw=str(error))
        self._remember("clear", result, clock_ms)
        if type(result) is not int or result != 0:
            raise ArmFault("controller_clear_unconfirmed", "recovery", "ClearError", result, result)
        after = self.snapshot(clock_ms)
        self._safe(after)
        if after["alarm_codes"]:
            raise ArmFault("controller_alarm_persists", "recovery", "fault_query", raw=after)
        before_raw, before_truncated = raw_evidence(before["alarm_codes"])
        return dict(after, before_raw_hex=before_raw, before_truncated=before_truncated,
                    before_sample_time_ms=before["sample_time_ms"], clear_vendor_code=result)

    def verify_recovery(self, clock_ms):
        state = self.snapshot(clock_ms)
        self._safe(state)
        if state["alarm_codes"]:
            raise ArmFault("controller_alarm_active", "recovery", "fault_query", raw=state)
        return state


def controller_state_payload(state):
    raw_hex, truncated = raw_evidence(state["alarm_codes"])
    items = [("controller_state", "alarm" if state["alarm_codes"] else "clear"),
                          ("stationary", int(state["stationary"])),
                          ("queue_empty", int(state["queue_empty"])),
                          ("emergency_stop", int(state["emergency_stop"])),
                          ("raw_hex", raw_hex), ("raw_truncated", truncated),
                          ("sample_time_ms", state["sample_time_ms"])]
    for key in ("before_raw_hex", "before_truncated", "before_sample_time_ms", "clear_vendor_code"):
        if key in state:
            items.append((key, state[key]))
    return encode_fields(items)
