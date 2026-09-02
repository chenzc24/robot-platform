"""Strict conversion of validated endpoint status replies into display state."""

from dataclasses import dataclass


class StatusMappingError(ValueError):
    """A response cannot safely be represented as a known device state."""


def _mapping(value, code):
    if not isinstance(value, dict):
        raise StatusMappingError(code)
    return value


def _exact(mapping, fields, code):
    if set(mapping) != set(fields):
        raise StatusMappingError(code)


def _token(value, code, allow_none=False):
    if not isinstance(value, str) or not value or len(value) > 64:
        raise StatusMappingError(code)
    if not allow_none and value == "none":
        raise StatusMappingError(code)
    return value


def _flag(value, code):
    if not isinstance(value, bool):
        raise StatusMappingError(code)
    return value


def _nonnegative_integer(value, code):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise StatusMappingError(code)
    return value


@dataclass(frozen=True)
class ChassisStatus:
    service_state: str
    chassis_state: str
    motion_permitted: bool
    authenticated: bool
    lease_active: bool
    lease_owner: str
    lease_remaining_ms: int
    hold_remaining_ms: int
    last_error: str

    @property
    def motion_enabled(self):
        return self.chassis_state in {"enabled_stopped", "moving"}


@dataclass(frozen=True)
class ArmStatus:
    service_state: str
    motion_permitted: bool
    control_mode: str
    active_sequence: int
    last_error: str
    terminal_position_supported: bool
    cancel_supported: bool


def parse_chassis_status(response):
    """Parse the exact RCP/TCP v2 `STATE` response shape."""
    response = _mapping(response, "invalid_chassis_status_response")
    _exact(response, ("version", "sequence", "type", "ttl_ms", "payload"), "invalid_chassis_status_response")
    sequence = _nonnegative_integer(response["sequence"], "invalid_chassis_status_response")
    if response["version"] != 2 or sequence == 0 or response["ttl_ms"] != 0 or response["type"] != "STATE":
        raise StatusMappingError("invalid_chassis_status_type")
    payload = _mapping(response["payload"], "invalid_chassis_status_payload")
    fields = (
        "service_state",
        "chassis_state",
        "motion_permitted",
        "authenticated",
        "lease_active",
        "lease_owner",
        "lease_remaining_ms",
        "hold_remaining_ms",
        "last_error",
    )
    _exact(payload, fields, "invalid_chassis_status_payload")
    lease_active = _flag(payload["lease_active"], "invalid_chassis_status_payload")
    owner = _token(payload["lease_owner"], "invalid_chassis_status_payload", allow_none=True)
    if (lease_active and owner == "none") or (not lease_active and owner != "none"):
        raise StatusMappingError("invalid_chassis_lease_state")
    return ChassisStatus(
        service_state=_token(payload["service_state"], "invalid_chassis_status_payload"),
        chassis_state=_token(payload["chassis_state"], "invalid_chassis_status_payload"),
        motion_permitted=_flag(payload["motion_permitted"], "invalid_chassis_status_payload"),
        authenticated=_flag(payload["authenticated"], "invalid_chassis_status_payload"),
        lease_active=lease_active,
        lease_owner=owner,
        lease_remaining_ms=_nonnegative_integer(payload["lease_remaining_ms"], "invalid_chassis_status_payload"),
        hold_remaining_ms=_nonnegative_integer(payload["hold_remaining_ms"], "invalid_chassis_status_payload"),
        last_error=_token(payload["last_error"], "invalid_chassis_status_payload", allow_none=True),
    )


def _fields(payload):
    if not isinstance(payload, str) or not payload:
        raise StatusMappingError("invalid_arm_status_payload")
    values = {}
    for item in payload.split(";"):
        if item.count("=") != 1:
            raise StatusMappingError("invalid_arm_status_payload")
        name, value = item.split("=", 1)
        if not name or not value or name in values:
            raise StatusMappingError("invalid_arm_status_payload")
        values[name] = value
    return values


def _binary(value):
    if value not in {"0", "1"}:
        raise StatusMappingError("invalid_arm_status_payload")
    return value == "1"


def parse_arm_status(responses):
    """Parse the terminal lifecycle response for the current RPA2 status service."""
    if not isinstance(responses, (list, tuple)) or not responses:
        raise StatusMappingError("invalid_arm_status_response")
    terminal = _mapping(responses[-1], "invalid_arm_status_response")
    fields = {
        "version",
        "kind",
        "message_id",
        "sequence",
        "target",
        "name",
        "ttl_ms",
        "payload",
        "correlation_id",
        "lifecycle",
    }
    _exact(terminal, fields, "invalid_arm_status_response")
    if terminal["kind"] != "lifecycle" or terminal["target"] != "arm" or terminal["name"] != "arm.status" or terminal["lifecycle"] != "DONE":
        raise StatusMappingError("invalid_arm_status_terminal")
    payload = _mapping(terminal["payload"], "invalid_arm_status_response")
    _exact(payload, ("downstream_sequence", "terminal_position", "downstream_payload"), "invalid_arm_status_response")
    _nonnegative_integer(payload["downstream_sequence"], "invalid_arm_status_response")
    values = _fields(payload["downstream_payload"])
    expected = {
        "service_state",
        "motion_enabled",
        "control_mode",
        "active_sequence",
        "last_error",
        "terminal_position_supported",
        "cancel_supported",
    }
    _exact(values, expected, "invalid_arm_status_payload")
    service_state = values["service_state"]
    if service_state not in {"ready", "running", "fault"}:
        raise StatusMappingError("invalid_arm_service_state")
    if values["control_mode"] not in {"production", "yolo"}:
        raise StatusMappingError("invalid_arm_control_mode")
    if not values["active_sequence"].isdigit():
        raise StatusMappingError("invalid_arm_status_payload")
    return ArmStatus(
        service_state=service_state,
        motion_permitted=_binary(values["motion_enabled"]),
        control_mode=values["control_mode"],
        active_sequence=int(values["active_sequence"]),
        last_error=_token(values["last_error"], "invalid_arm_status_payload", allow_none=True),
        terminal_position_supported=_binary(values["terminal_position_supported"]),
        cancel_supported=_binary(values["cancel_supported"]),
    )
