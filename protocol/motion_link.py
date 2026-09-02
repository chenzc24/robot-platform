"""Strict ASCII framing shared by the RPA2 arm link.

This module deliberately does not know controller APIs; it only protects the
serial/TCP232 byte boundary.
"""


MAX_FRAME_BYTES = 512
MAX_SEQUENCE = 2147483647
REQUEST_TYPES = ("PING", "STATUS", "MOVEJ", "MOVEL", "RELJOINT", "RELLINEAR", "GRIPPER")
RESPONSE_TYPES = ("PONG", "STATE", "ACK", "RUNNING", "DONE", "ERROR")


class MotionLinkError(ValueError):
    def __init__(self, code):
        ValueError.__init__(self, code)
        self.code = code


def crc16_ccitt(data):
    crc = 0xFFFF
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def _sequence(sequence):
    if isinstance(sequence, bool) or not isinstance(sequence, int) or not 1 <= sequence <= MAX_SEQUENCE:
        raise MotionLinkError("invalid_sequence")


def _payload(payload):
    if not isinstance(payload, str) or any(ord(char) < 32 or ord(char) > 126 or char in "|\r\n" for char in payload):
        raise MotionLinkError("invalid_payload")
    return payload


def encode_frame(marker, message_type, sequence, ttl_ms, payload=""):
    if marker != "RPA2":
        raise MotionLinkError("invalid_marker")
    if message_type not in REQUEST_TYPES + RESPONSE_TYPES:
        raise MotionLinkError("unsupported_type")
    _sequence(sequence)
    if isinstance(ttl_ms, bool) or not isinstance(ttl_ms, int) or not 0 <= ttl_ms <= 60000:
        raise MotionLinkError("invalid_ttl")
    if message_type in RESPONSE_TYPES and ttl_ms != 0:
        raise MotionLinkError("invalid_response_ttl")
    body = "%s|%s|%d|%d|%s|" % (marker, message_type, sequence, ttl_ms, _payload(payload))
    result = body.encode("ascii") + ("%04X\n" % crc16_ccitt(body.encode("ascii"))).encode("ascii")
    if len(result) > MAX_FRAME_BYTES:
        raise MotionLinkError("frame_too_long")
    return result


def decode_frame(frame):
    if not isinstance(frame, (bytes, bytearray)) or len(frame) > MAX_FRAME_BYTES:
        raise MotionLinkError("frame_too_long")
    if not frame.endswith(b"\n") or b"\r" in frame:
        raise MotionLinkError("invalid_terminator")
    try:
        pieces = frame[:-1].decode("ascii").split("|")
    except UnicodeError:
        raise MotionLinkError("non_ascii_frame")
    if len(pieces) != 6:
        raise MotionLinkError("invalid_format")
    marker, message_type, sequence_text, ttl_text, payload, crc_text = pieces
    if marker != "RPA2" or message_type not in REQUEST_TYPES + RESPONSE_TYPES:
        raise MotionLinkError("unsupported_type")
    if not sequence_text.isdigit() or not ttl_text.isdigit() or len(crc_text) != 4:
        raise MotionLinkError("invalid_format")
    sequence, ttl_ms = int(sequence_text), int(ttl_text)
    _sequence(sequence)
    _payload(payload)
    if any(char not in "0123456789ABCDEF" for char in crc_text):
        raise MotionLinkError("invalid_crc")
    body = ("|".join(pieces[:5]) + "|").encode("ascii")
    if crc16_ccitt(body) != int(crc_text, 16):
        raise MotionLinkError("crc_mismatch")
    if message_type in RESPONSE_TYPES and ttl_ms != 0:
        raise MotionLinkError("invalid_response_ttl")
    return {"marker": marker, "type": message_type, "sequence": sequence, "ttl_ms": ttl_ms, "payload": payload}


def encode_fields(items):
    fields = []
    for key, value in items:
        if not isinstance(key, str) or not key or any(char not in "abcdefghijklmnopqrstuvwxyz_" for char in key):
            raise MotionLinkError("invalid_field_name")
        value = str(value)
        if not value or any(char in "=;|\r\n" or ord(char) < 32 or ord(char) > 126 for char in value):
            raise MotionLinkError("invalid_field_value")
        fields.append(key + "=" + value)
    return ";".join(fields)


def decode_fields(payload, expected):
    if expected == ():
        if payload:
            raise MotionLinkError("unexpected_payload")
        return {}
    values = {}
    for item in payload.split(";"):
        if item.count("=") != 1:
            raise MotionLinkError("invalid_payload_fields")
        key, value = item.split("=", 1)
        if not key or not value or key in values:
            raise MotionLinkError("invalid_payload_fields")
        values[key] = value
    if tuple(values) != tuple(expected):
        raise MotionLinkError("invalid_payload_fields")
    return values


class FrameStreamDecoder:
    def __init__(self, marker="RPA2"):
        if marker != "RPA2":
            raise ValueError("unsupported marker")
        self._buffer = bytearray()
        self._discarding = False

    def feed(self, data):
        if not isinstance(data, (bytes, bytearray)):
            raise MotionLinkError("invalid_frame_type")
        frames, errors = [], []
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
            elif byte == 10:
                raw, self._buffer = bytes(self._buffer), bytearray()
                try:
                    frames.append(decode_frame(raw))
                except MotionLinkError as error:
                    errors.append(error.code)
        return frames, errors
