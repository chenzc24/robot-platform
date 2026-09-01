"""Strict NDJSON envelope used between the computer and MaixCam.

The envelope carries task intent only.  It is never passed transparently to a
motor controller or the robot arm.
"""

import json


MAX_FRAME_BYTES = 4096
MAX_SEQUENCE = 2147483647
KINDS = ("command", "lifecycle", "status", "event")
LIFECYCLES = ("RECEIVED", "ACCEPTED", "RUNNING", "DONE", "FAULT", "REJECTED", "UNKNOWN")


class EnvelopeError(ValueError):
    def __init__(self, code):
        ValueError.__init__(self, code)
        self.code = code


def _integer(value, low, high, code):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise EnvelopeError(code)
    return value


def _identifier(value, code):
    if not isinstance(value, str) or not value or len(value) > 128:
        raise EnvelopeError(code)
    return value


def validate_message(message):
    """Return a checked message without normalizing missing or extra fields."""
    if not isinstance(message, dict):
        raise EnvelopeError("invalid_message")
    kind = message.get("kind")
    if kind not in KINDS:
        raise EnvelopeError("invalid_kind")
    required = {"version", "kind", "message_id", "sequence", "target", "name", "ttl_ms", "payload"}
    if kind == "lifecycle":
        required |= {"correlation_id", "lifecycle"}
    if set(message) != required:
        raise EnvelopeError("invalid_fields")
    _integer(message["version"], 1, 1, "unsupported_version")
    _identifier(message["message_id"], "invalid_message_id")
    _integer(message["sequence"], 1, MAX_SEQUENCE, "invalid_sequence")
    _identifier(message["target"], "invalid_target")
    _identifier(message["name"], "invalid_name")
    if not isinstance(message["payload"], dict):
        raise EnvelopeError("invalid_payload")
    if kind == "command":
        _integer(message["ttl_ms"], 100, 60000, "invalid_ttl")
    elif message["ttl_ms"] != 0:
        raise EnvelopeError("invalid_response_ttl")
    if kind == "lifecycle":
        _identifier(message["correlation_id"], "invalid_correlation_id")
        if message["lifecycle"] not in LIFECYCLES:
            raise EnvelopeError("invalid_lifecycle")
    return message


def encode_message(message):
    validate_message(message)
    try:
        encoded = json.dumps(message, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii") + b"\n"
    except (TypeError, ValueError):
        raise EnvelopeError("not_json_serializable")
    if len(encoded) > MAX_FRAME_BYTES:
        raise EnvelopeError("frame_too_long")
    return encoded


def lifecycle(command, lifecycle_name, payload=None, *, name=None):
    """Create a lifecycle response correlated to one accepted command."""
    if lifecycle_name not in LIFECYCLES:
        raise EnvelopeError("invalid_lifecycle")
    validate_message(command)
    if command["kind"] != "command":
        raise EnvelopeError("command_required")
    return {
        "version": 1,
        "kind": "lifecycle",
        "message_id": command["message_id"] + ":" + lifecycle_name.lower(),
        "sequence": command["sequence"],
        "target": command["target"],
        "name": name or command["name"],
        "ttl_ms": 0,
        "payload": payload or {},
        "correlation_id": command["message_id"],
        "lifecycle": lifecycle_name,
    }


class EnvelopeStreamDecoder:
    """Decode complete ASCII NDJSON frames and discard oversized lines."""

    def __init__(self):
        self._buffer = bytearray()
        self._discarding = False

    def feed(self, data):
        if not isinstance(data, (bytes, bytearray)):
            raise EnvelopeError("invalid_frame_type")
        messages, errors = [], []
        for byte in data:
            if self._discarding:
                if byte == 10:
                    self._discarding = False
                continue
            self._buffer.append(byte)
            if len(self._buffer) > MAX_FRAME_BYTES:
                self._buffer = bytearray()
                self._discarding = byte != 10
                errors.append("frame_too_long")
                continue
            if byte != 10:
                continue
            raw = bytes(self._buffer[:-1])
            self._buffer = bytearray()
            try:
                if b"\r" in raw:
                    raise EnvelopeError("invalid_terminator")
                value = json.loads(raw.decode("ascii"))
                messages.append(validate_message(value))
            except (UnicodeError, ValueError, TypeError, EnvelopeError) as error:
                errors.append(getattr(error, "code", "invalid_json"))
        return messages, errors
