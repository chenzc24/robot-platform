"""MicroPython-compatible RCP1/TCP framing for the chassis runtime link."""

try:
    import ujson as json
except ImportError:
    import json


PROTOCOL_VERSION = 1
MAX_FRAME_BYTES = 512
MAX_SEQUENCE = 2147483647
MIN_REQUEST_TTL_MS = 100
MAX_REQUEST_TTL_MS = 5000
MAX_CLIENT_ID_BYTES = 32

REQUEST_TYPES = ("HELLO", "PING", "STATUS")
RESPONSE_TYPES = ("WELCOME", "PONG", "STATE", "ERROR")
VALID_TYPES = REQUEST_TYPES + RESPONSE_TYPES


class ChassisTcpFrameError(ValueError):
    """Describe a rejected frame without retaining its raw contents."""

    def __init__(self, code):
        ValueError.__init__(self, code)
        self.code = code


def _identifier(value, code, max_bytes=32):
    if not isinstance(value, str):
        raise ChassisTcpFrameError(code)
    try:
        encoded = value.encode("ascii")
    except UnicodeError:
        raise ChassisTcpFrameError(code)
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789_-"
    if not encoded or len(encoded) > max_bytes:
        raise ChassisTcpFrameError(code)
    if value[0] < "a" or value[0] > "z":
        raise ChassisTcpFrameError(code)
    if not all(character in allowed for character in value):
        raise ChassisTcpFrameError(code)
    return value


def _validate_sequence(sequence):
    if isinstance(sequence, bool) or not isinstance(sequence, int):
        raise ChassisTcpFrameError("invalid_sequence")
    if sequence < 1 or sequence > MAX_SEQUENCE:
        raise ChassisTcpFrameError("invalid_sequence")


def _validate_ttl(message_type, ttl_ms):
    if isinstance(ttl_ms, bool) or not isinstance(ttl_ms, int):
        raise ChassisTcpFrameError("invalid_ttl")
    if message_type in REQUEST_TYPES:
        if ttl_ms < MIN_REQUEST_TTL_MS or ttl_ms > MAX_REQUEST_TTL_MS:
            raise ChassisTcpFrameError("invalid_ttl")
    elif ttl_ms != 0:
        raise ChassisTcpFrameError("invalid_ttl")


def _validate_payload(message_type, payload):
    if not isinstance(payload, dict):
        raise ChassisTcpFrameError("invalid_payload")
    if message_type == "HELLO":
        if set(payload) != {"client"}:
            raise ChassisTcpFrameError("invalid_payload")
        return {"client": _identifier(payload["client"], "invalid_client")}
    if message_type in ("PING", "STATUS"):
        if payload:
            raise ChassisTcpFrameError("invalid_payload")
        return {}
    if message_type == "WELCOME":
        expected = {"service": "chassis", "motion_enabled": False}
        if payload != expected:
            raise ChassisTcpFrameError("invalid_payload")
        return expected
    if message_type == "PONG":
        expected = {"protocol": PROTOCOL_VERSION}
        if payload != expected:
            raise ChassisTcpFrameError("invalid_payload")
        return expected
    if message_type == "STATE":
        expected = {"service": "safe_idle", "motion_enabled": False}
        if payload != expected:
            raise ChassisTcpFrameError("invalid_payload")
        return expected
    if message_type == "ERROR":
        if set(payload) != {"code"}:
            raise ChassisTcpFrameError("invalid_payload")
        return {"code": _identifier(payload["code"], "invalid_error_code")}
    raise ChassisTcpFrameError("unsupported_type")


def validate_message(message):
    """Validate one decoded message and return a normalized copy."""
    if not isinstance(message, dict):
        raise ChassisTcpFrameError("invalid_message")
    required = {"version", "sequence", "type", "ttl_ms", "payload"}
    if set(message) != required:
        raise ChassisTcpFrameError("invalid_fields")
    if message["version"] != PROTOCOL_VERSION or isinstance(
        message["version"], bool
    ):
        raise ChassisTcpFrameError("unsupported_version")
    message_type = message["type"]
    if message_type not in VALID_TYPES:
        raise ChassisTcpFrameError("unsupported_type")
    _validate_sequence(message["sequence"])
    _validate_ttl(message_type, message["ttl_ms"])
    payload = _validate_payload(message_type, message["payload"])
    return {
        "version": PROTOCOL_VERSION,
        "sequence": message["sequence"],
        "type": message_type,
        "ttl_ms": message["ttl_ms"],
        "payload": payload,
    }


def _payload_text(message_type, payload):
    if message_type == "HELLO":
        return '{"client":"%s"}' % payload["client"]
    if message_type in ("PING", "STATUS"):
        return "{}"
    if message_type == "WELCOME":
        return '{"service":"chassis","motion_enabled":false}'
    if message_type == "PONG":
        return '{"protocol":%d}' % PROTOCOL_VERSION
    if message_type == "STATE":
        return '{"service":"safe_idle","motion_enabled":false}'
    if message_type == "ERROR":
        return '{"code":"%s"}' % payload["code"]
    raise ChassisTcpFrameError("unsupported_type")


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
        raise ChassisTcpFrameError("frame_too_long")
    return frame


def decode_message(frame):
    """Decode and validate one complete newline-delimited JSON frame."""
    if not isinstance(frame, (bytes, bytearray)):
        raise ChassisTcpFrameError("invalid_frame_type")
    frame = bytes(frame)
    if len(frame) > MAX_FRAME_BYTES:
        raise ChassisTcpFrameError("frame_too_long")
    if not frame.endswith(b"\n") or b"\r" in frame:
        raise ChassisTcpFrameError("invalid_terminator")
    try:
        text = frame[:-1].decode("ascii")
    except UnicodeError:
        raise ChassisTcpFrameError("non_ascii_frame")
    try:
        message = json.loads(text)
    except (TypeError, ValueError):
        raise ChassisTcpFrameError("invalid_json")
    return validate_message(message)


class MessageStreamDecoder:
    """Recover bounded messages from fragmented or combined TCP reads."""

    def __init__(self):
        self._buffer = bytearray()
        self._discarding = False

    def feed(self, data):
        if not isinstance(data, (bytes, bytearray)):
            raise ChassisTcpFrameError("invalid_frame_type")
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
            except ChassisTcpFrameError as error:
                errors.append(error.code)
        return messages, errors
