"""MicroPython-compatible RCP/TCP v3 framing for direct chassis motion."""

try:
    import ujson as json
except ImportError:
    import json


PROTOCOL_VERSION = 3
MAX_FRAME_BYTES = 512
MAX_SEQUENCE = 2147483647
MIN_REQUEST_TTL_MS = 100
MAX_REQUEST_TTL_MS = 5000
MIN_HOLD_MS = 100
MAX_HOLD_MS = 500
MAX_LINEAR_MM_S = 600
MAX_OMEGA_MRAD_S = 800
MIN_CREDENTIAL_BYTES = 16
MAX_CREDENTIAL_BYTES = 64

QUERY_TYPES = ("HELLO", "PING", "STATUS")
CONTROL_TYPES = (
    "ENABLE",
    "VELOCITY",
    "STOP",
    "DISABLE",
)
REQUEST_TYPES = QUERY_TYPES + CONTROL_TYPES
RESPONSE_TYPES = ("WELCOME", "PONG", "STATE", "ACK", "DONE", "ERROR")
VALID_TYPES = REQUEST_TYPES + RESPONSE_TYPES


class ChassisTcpV3FrameError(ValueError):
    """Describe a rejected frame without retaining raw input or credentials."""

    def __init__(self, code):
        ValueError.__init__(self, code)
        self.code = code


def _integer(value, low, high, code):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ChassisTcpV3FrameError(code)
    if value < low or value > high:
        raise ChassisTcpV3FrameError(code)
    return value


def _boolean(value, code):
    if not isinstance(value, bool):
        raise ChassisTcpV3FrameError(code)
    return value


def _token(value, code, max_bytes=64, allow_none=False):
    if allow_none and value == "none":
        return value
    if not isinstance(value, str):
        raise ChassisTcpV3FrameError(code)
    try:
        encoded = value.encode("ascii")
    except UnicodeError:
        raise ChassisTcpV3FrameError(code)
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789_.-"
    if not encoded or len(encoded) > max_bytes:
        raise ChassisTcpV3FrameError(code)
    if value[0] < "a" or value[0] > "z":
        raise ChassisTcpV3FrameError(code)
    if not all(character in allowed for character in value):
        raise ChassisTcpV3FrameError(code)
    return value


def _credential(value):
    if not isinstance(value, str):
        raise ChassisTcpV3FrameError("invalid_credential")
    try:
        encoded = value.encode("ascii")
    except UnicodeError:
        raise ChassisTcpV3FrameError("invalid_credential")
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
    if len(encoded) < MIN_CREDENTIAL_BYTES or len(encoded) > MAX_CREDENTIAL_BYTES:
        raise ChassisTcpV3FrameError("invalid_credential")
    if not all(character in allowed for character in value):
        raise ChassisTcpV3FrameError("invalid_credential")
    return value


def _exact(payload, fields):
    if not isinstance(payload, dict) or set(payload) != set(fields):
        raise ChassisTcpV3FrameError("invalid_payload")


def _validate_payload(message_type, payload):
    if message_type == "HELLO":
        _exact(payload, ("client", "credential"))
        return {
            "client": _token(payload["client"], "invalid_client", 32),
            "credential": _credential(payload["credential"]),
        }
    if message_type in ("PING", "STATUS", "ENABLE", "STOP", "DISABLE"):
        _exact(payload, ())
        return {}
    if message_type == "VELOCITY":
        _exact(payload, ("vx_mm_s", "vy_mm_s", "omega_mrad_s", "hold_ms"))
        return {
            "vx_mm_s": _integer(
                payload["vx_mm_s"], -MAX_LINEAR_MM_S, MAX_LINEAR_MM_S, "invalid_velocity"
            ),
            "vy_mm_s": _integer(
                payload["vy_mm_s"], -MAX_LINEAR_MM_S, MAX_LINEAR_MM_S, "invalid_velocity"
            ),
            "omega_mrad_s": _integer(
                payload["omega_mrad_s"],
                -MAX_OMEGA_MRAD_S,
                MAX_OMEGA_MRAD_S,
                "invalid_velocity",
            ),
            "hold_ms": _integer(
                payload["hold_ms"], MIN_HOLD_MS, MAX_HOLD_MS, "invalid_hold"
            ),
        }
    if message_type == "WELCOME":
        _exact(payload, ("service", "protocol", "motion_permitted"))
        if payload["service"] != "chassis" or payload["protocol"] != PROTOCOL_VERSION:
            raise ChassisTcpV3FrameError("invalid_payload")
        return {
            "service": "chassis",
            "protocol": PROTOCOL_VERSION,
            "motion_permitted": _boolean(
                payload["motion_permitted"], "invalid_payload"
            ),
        }
    if message_type == "PONG":
        _exact(payload, ("protocol",))
        if payload["protocol"] != PROTOCOL_VERSION:
            raise ChassisTcpV3FrameError("invalid_payload")
        return {"protocol": PROTOCOL_VERSION}
    if message_type == "STATE":
        fields = (
            "service_state",
            "chassis_state",
            "motion_permitted",
            "authenticated",
            "hold_remaining_ms",
            "last_error",
        )
        _exact(payload, fields)
        return {
            "service_state": _token(payload["service_state"], "invalid_state", 32),
            "chassis_state": _token(payload["chassis_state"], "invalid_state", 32),
            "motion_permitted": _boolean(payload["motion_permitted"], "invalid_state"),
            "authenticated": _boolean(payload["authenticated"], "invalid_state"),
            "hold_remaining_ms": _integer(
                payload["hold_remaining_ms"], 0, MAX_HOLD_MS, "invalid_state"
            ),
            "last_error": _token(payload["last_error"], "invalid_state", 64, True),
        }
    if message_type in ("ACK", "DONE"):
        _exact(payload, ("command", "state"))
        command = payload["command"]
        if command not in CONTROL_TYPES:
            raise ChassisTcpV3FrameError("invalid_payload")
        return {
            "command": command,
            "state": _token(payload["state"], "invalid_state", 32),
        }
    if message_type == "ERROR":
        _exact(payload, ("code", "retryable"))
        return {
            "code": _token(payload["code"], "invalid_error_code", 64),
            "retryable": _boolean(payload["retryable"], "invalid_payload"),
        }
    raise ChassisTcpV3FrameError("unsupported_type")


def validate_message(message):
    """Validate one decoded message and return a normalized copy."""
    if not isinstance(message, dict):
        raise ChassisTcpV3FrameError("invalid_message")
    required = {"version", "sequence", "type", "ttl_ms", "payload"}
    if set(message) != required:
        raise ChassisTcpV3FrameError("invalid_fields")
    if message["version"] != PROTOCOL_VERSION or isinstance(message["version"], bool):
        raise ChassisTcpV3FrameError("unsupported_version")
    message_type = message["type"]
    if message_type not in VALID_TYPES:
        raise ChassisTcpV3FrameError("unsupported_type")
    sequence = _integer(message["sequence"], 1, MAX_SEQUENCE, "invalid_sequence")
    ttl_ms = message["ttl_ms"]
    if message_type in REQUEST_TYPES:
        ttl_ms = _integer(
            ttl_ms, MIN_REQUEST_TTL_MS, MAX_REQUEST_TTL_MS, "invalid_ttl"
        )
    elif ttl_ms != 0 or isinstance(ttl_ms, bool):
        raise ChassisTcpV3FrameError("invalid_ttl")
    return {
        "version": PROTOCOL_VERSION,
        "sequence": sequence,
        "type": message_type,
        "ttl_ms": ttl_ms,
        "payload": _validate_payload(message_type, message["payload"]),
    }


def _payload_text(message_type, payload):
    if message_type == "HELLO":
        return '{"client":"%s","credential":"%s"}' % (
            payload["client"],
            payload["credential"],
        )
    if message_type in ("PING", "STATUS", "ENABLE", "STOP", "DISABLE"):
        return "{}"
    if message_type == "VELOCITY":
        return (
            '{"vx_mm_s":%d,"vy_mm_s":%d,"omega_mrad_s":%d,"hold_ms":%d}'
            % (
                payload["vx_mm_s"],
                payload["vy_mm_s"],
                payload["omega_mrad_s"],
                payload["hold_ms"],
            )
        )
    if message_type == "WELCOME":
        return '{"service":"chassis","protocol":3,"motion_permitted":%s}' % (
            "true" if payload["motion_permitted"] else "false"
        )
    if message_type == "PONG":
        return '{"protocol":3}'
    if message_type == "STATE":
        return (
            '{"service_state":"%s","chassis_state":"%s",'
            '"motion_permitted":%s,"authenticated":%s,'
            '"hold_remaining_ms":%d,"last_error":"%s"}'
            % (
                payload["service_state"],
                payload["chassis_state"],
                "true" if payload["motion_permitted"] else "false",
                "true" if payload["authenticated"] else "false",
                payload["hold_remaining_ms"],
                payload["last_error"],
            )
        )
    if message_type in ("ACK", "DONE"):
        return '{"command":"%s","state":"%s"}' % (
            payload["command"],
            payload["state"],
        )
    if message_type == "ERROR":
        return '{"code":"%s","retryable":%s}' % (
            payload["code"],
            "true" if payload["retryable"] else "false",
        )
    raise ChassisTcpV3FrameError("unsupported_type")


def encode_message(message_type, sequence, ttl_ms, payload=None):
    """Encode one canonical ASCII JSON line."""
    message = validate_message(
        {
            "version": PROTOCOL_VERSION,
            "sequence": sequence,
            "type": message_type,
            "ttl_ms": ttl_ms,
            "payload": {} if payload is None else payload,
        }
    )
    text = (
        '{"version":%d,"sequence":%d,"type":"%s","ttl_ms":%d,"payload":%s}\n'
        % (
            message["version"],
            message["sequence"],
            message["type"],
            message["ttl_ms"],
            _payload_text(message["type"], message["payload"]),
        )
    )
    frame = text.encode("ascii")
    if len(frame) > MAX_FRAME_BYTES:
        raise ChassisTcpV3FrameError("frame_too_long")
    return frame


def decode_message(frame):
    """Decode and validate one complete newline-delimited JSON frame."""
    if not isinstance(frame, (bytes, bytearray)):
        raise ChassisTcpV3FrameError("invalid_frame_type")
    frame = bytes(frame)
    if len(frame) > MAX_FRAME_BYTES:
        raise ChassisTcpV3FrameError("frame_too_long")
    if not frame.endswith(b"\n") or b"\r" in frame:
        raise ChassisTcpV3FrameError("invalid_terminator")
    try:
        text = frame[:-1].decode("ascii")
    except UnicodeError:
        raise ChassisTcpV3FrameError("non_ascii_frame")
    try:
        message = json.loads(text)
    except (TypeError, ValueError):
        raise ChassisTcpV3FrameError("invalid_json")
    return validate_message(message)


class MessageStreamDecoder:
    """Recover bounded v3 messages from fragmented or combined TCP reads."""

    def __init__(self):
        self._buffer = bytearray()
        self._discarding = False

    def feed(self, data):
        if not isinstance(data, (bytes, bytearray)):
            raise ChassisTcpV3FrameError("invalid_frame_type")
        messages = []
        errors = []
        for value in data:
            if self._discarding:
                if value == 10:
                    self._discarding = False
                continue
            self._buffer.append(value)
            if len(self._buffer) > MAX_FRAME_BYTES:
                self._buffer = bytearray()
                self._discarding = value != 10
                errors.append("frame_too_long")
                continue
            if value != 10:
                continue
            frame = bytes(self._buffer)
            self._buffer = bytearray()
            try:
                messages.append(decode_message(frame))
            except ChassisTcpV3FrameError as error:
                errors.append(error.code)
        return messages, errors
