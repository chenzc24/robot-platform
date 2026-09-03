"""Strict parsing of arm fault-v1 data; vendor codes remain namespaced evidence."""

from runtime_core import ensure_runtime_import_paths

ensure_runtime_import_paths()
from motion_link import decode_fault, decode_fields


def raw_payload(responses):
    return responses[-1]["payload"]["downstream_payload"]


def capabilities(payload):
    fields = decode_fields(payload, ("fault_version", "xyz_preflight", "controller_query", "controller_clear", "service_recover"))
    if fields.pop("fault_version") != "1" or any(value not in ("0", "1") for value in fields.values()):
        raise ValueError("invalid_fault_capabilities")
    result = {key: value == "1" for key, value in fields.items()}
    if (result["controller_clear"] or result["service_recover"]) and not result["controller_query"]:
        raise ValueError("invalid_fault_capabilities")
    return dict(result, fault_version=1)


def fault(payload):
    fields = decode_fault(payload)
    if "vendor_code" not in fields:
        return dict(fields, legacy=True)
    return dict(fields, vendor_code=None if fields["vendor_code"] == "unknown" else int(fields["vendor_code"]),
                retryable=False, sample_time_ms=int(fields["sample_time_ms"]), fault_id=int(fields["fault_id"]),
                raw_truncated=fields["raw_truncated"] == "1",
                raw_text=bytes.fromhex(fields["raw_hex"]).decode("utf-8", errors="replace"),
                clock_domain="controller_local_ms")


def controller_state(payload, cleared=False):
    expected = ("controller_state", "stationary", "queue_empty", "emergency_stop", "raw_hex", "raw_truncated", "sample_time_ms")
    if cleared:
        expected += ("before_raw_hex", "before_truncated", "before_sample_time_ms", "clear_vendor_code")
    fields = decode_fields(payload, expected)
    if fields["controller_state"] not in ("alarm", "clear"):
        raise ValueError("invalid_controller_fault_state")
    for key in ("stationary", "queue_empty", "emergency_stop", "raw_truncated"):
        if fields[key] not in ("0", "1"):
            raise ValueError("invalid_controller_fault_state")
    if not fields["sample_time_ms"].isdigit() or len(fields["sample_time_ms"]) > 19:
        raise ValueError("invalid_controller_fault_timestamp")
    raw = fields["raw_hex"]
    if not 2 <= len(raw) <= 128 or len(raw) % 2 or any(c not in "0123456789abcdef" for c in raw):
        raise ValueError("invalid_controller_fault_raw")
    if cleared:
        before = fields["before_raw_hex"]
        if (fields["clear_vendor_code"] != "0" or fields["before_truncated"] not in ("0", "1")
                or not fields["before_sample_time_ms"].isdigit() or len(fields["before_sample_time_ms"]) > 19
                or not 2 <= len(before) <= 128 or len(before) % 2
                or any(c not in "0123456789abcdef" for c in before)):
            raise ValueError("invalid_clear_evidence")
        fields["before_raw_text"] = bytes.fromhex(before).decode("utf-8", errors="replace")
    return dict(fields, sample_time_ms=int(fields["sample_time_ms"]),
                raw_text=bytes.fromhex(raw).decode("utf-8", errors="replace"),
                clock_domain="controller_local_ms",
                **{key: fields[key] == "1" for key in ("stationary", "queue_empty", "emergency_stop", "raw_truncated")})
