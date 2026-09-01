"""Framing for the bounded MaixCam to arm validation link."""


PROTOCOL_MARKER = "RPA1"
MAX_FRAME_BYTES = 96
MAX_SEQUENCE = 2147483647
VALID_TYPES = ("PING", "PONG", "STEP", "DONE", "ERROR")


class ArmFrameError(ValueError):
    """Describe a rejected frame without retaining raw input."""

    def __init__(self, code):
        ValueError.__init__(self, code)
        self.code = code


def crc16_ccitt(data):
    crc = 0xFFFF
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def _validate_sequence(sequence):
    if isinstance(sequence, bool) or not isinstance(sequence, int):
        raise ArmFrameError("invalid_sequence")
    if sequence < 1 or sequence > MAX_SEQUENCE:
        raise ArmFrameError("invalid_sequence")


def _validate_payload(message_type, payload):
    if not isinstance(payload, str):
        raise ArmFrameError("invalid_payload")
    if message_type in ("PING", "PONG", "STEP", "DONE"):
        if payload:
            raise ArmFrameError("invalid_payload")
        return
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789_"
    if not payload or payload[0] < "a" or payload[0] > "z":
        raise ArmFrameError("invalid_payload")
    if not all(character in allowed for character in payload):
        raise ArmFrameError("invalid_payload")


def encode_frame(message_type, sequence, payload=""):
    if message_type not in VALID_TYPES:
        raise ArmFrameError("unsupported_type")
    _validate_sequence(sequence)
    _validate_payload(message_type, payload)
    body = "%s|%s|%d|%s|" % (
        PROTOCOL_MARKER,
        message_type,
        sequence,
        payload,
    )
    body_bytes = body.encode("ascii")
    frame = body_bytes + ("%04X\n" % crc16_ccitt(body_bytes)).encode("ascii")
    if len(frame) > MAX_FRAME_BYTES:
        raise ArmFrameError("frame_too_long")
    return frame


def decode_frame(frame):
    if not isinstance(frame, (bytes, bytearray)):
        raise ArmFrameError("invalid_frame_type")
    frame = bytes(frame)
    if len(frame) > MAX_FRAME_BYTES:
        raise ArmFrameError("frame_too_long")
    if not frame.endswith(b"\n") or b"\r" in frame:
        raise ArmFrameError("invalid_terminator")
    try:
        text = frame[:-1].decode("ascii")
    except UnicodeError:
        raise ArmFrameError("non_ascii_frame")
    parts = text.split("|")
    if len(parts) != 5 or parts[0] != PROTOCOL_MARKER:
        raise ArmFrameError("invalid_format")
    message_type, sequence_text, payload, crc_text = parts[1:]
    if message_type not in VALID_TYPES:
        raise ArmFrameError("unsupported_type")
    if not sequence_text.isdigit():
        raise ArmFrameError("invalid_sequence")
    sequence = int(sequence_text)
    _validate_sequence(sequence)
    _validate_payload(message_type, payload)
    if len(crc_text) != 4 or not all(
        character in "0123456789ABCDEF" for character in crc_text
    ):
        raise ArmFrameError("invalid_crc")
    body = ("|".join(parts[:4]) + "|").encode("ascii")
    if crc16_ccitt(body) != int(crc_text, 16):
        raise ArmFrameError("crc_mismatch")
    return {"type": message_type, "sequence": sequence, "payload": payload}


class FrameStreamDecoder:
    """Recover complete frames from arbitrary serial chunks."""

    def __init__(self):
        self._buffer = bytearray()
        self._discarding = False

    def feed(self, data):
        if not isinstance(data, (bytes, bytearray)):
            raise ArmFrameError("invalid_frame_type")
        frames = []
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
            raw_frame = bytes(self._buffer)
            self._buffer = bytearray()
            try:
                frames.append(decode_frame(raw_frame))
            except ArmFrameError as error:
                errors.append(error.code)
        return frames, errors
