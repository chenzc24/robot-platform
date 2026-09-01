"""Standalone LAN1 responder for one fixed low-speed validation step."""


PROTOCOL_MARKER = "RPA1"
MAX_FRAME_BYTES = 96
MAX_SEQUENCE = 2147483647


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


def encode_frame(message_type, sequence, payload=""):
    body = "%s|%s|%d|%s|" % (
        PROTOCOL_MARKER,
        message_type,
        sequence,
        payload,
    )
    return body + "%04X\n" % crc16_ccitt(body.encode("ascii"))


def api_failed(result):
    if result is None:
        return False
    if isinstance(result, tuple):
        return bool(result[0]) if result else False
    return bool(result)


def decode_request(frame):
    if isinstance(frame, str):
        try:
            frame = frame.encode("ascii")
        except UnicodeError:
            return None, "non_ascii_frame"
    if not isinstance(frame, (bytes, bytearray)):
        return None, "invalid_frame_type"
    frame = bytes(frame)
    if len(frame) > MAX_FRAME_BYTES:
        return None, "frame_too_long"
    if not frame.endswith(b"\n") or b"\r" in frame:
        return None, "invalid_terminator"
    try:
        text = frame[:-1].decode("ascii")
    except UnicodeError:
        return None, "non_ascii_frame"
    parts = text.split("|")
    if len(parts) != 5 or parts[0] != PROTOCOL_MARKER:
        return None, "invalid_format"
    message_type, sequence_text, payload, crc_text = parts[1:]
    if not sequence_text.isdigit():
        return None, "invalid_sequence"
    sequence = int(sequence_text)
    if sequence < 1 or sequence > MAX_SEQUENCE:
        return None, "invalid_sequence"
    if len(crc_text) != 4 or not all(
        character in "0123456789ABCDEF" for character in crc_text
    ):
        return None, "invalid_crc"
    body = ("|".join(parts[:4]) + "|").encode("ascii")
    if crc16_ccitt(body) != int(crc_text, 16):
        return None, "crc_mismatch"
    if payload:
        return {"sequence": sequence}, "motion_disabled"
    if message_type not in ("PING", "STEP"):
        return {"sequence": sequence}, "motion_disabled"
    return {"type": message_type, "sequence": sequence}, None


class DiagnosticSession:
    def __init__(self, fixed_step=None):
        self._buffer = bytearray()
        self._discarding = False
        self._fixed_step = fixed_step
        self._step_consumed = False

    def feed(self, data):
        if isinstance(data, str):
            try:
                data = data.encode("ascii")
            except UnicodeError:
                return []
        if not isinstance(data, (bytes, bytearray)):
            return []
        responses = []
        for value in data:
            if self._discarding:
                if value == 10:
                    self._discarding = False
                continue
            self._buffer.append(value)
            if len(self._buffer) > MAX_FRAME_BYTES:
                self._buffer = bytearray()
                self._discarding = value != 10
                continue
            if value != 10:
                continue
            frame = bytes(self._buffer)
            self._buffer = bytearray()
            request, error = decode_request(frame)
            if request is None:
                continue
            if error is not None:
                responses.append(
                    encode_frame("ERROR", request["sequence"], error)
                )
            elif request["type"] == "PING":
                responses.append(encode_frame("PONG", request["sequence"]))
            elif self._step_consumed:
                responses.append(
                    encode_frame(
                        "ERROR", request["sequence"], "motion_already_consumed"
                    )
                )
            elif self._fixed_step is None:
                responses.append(
                    encode_frame("ERROR", request["sequence"], "motion_disabled")
                )
            else:
                self._step_consumed = True
                try:
                    self._fixed_step()
                except Exception:
                    responses.append(
                        encode_frame("ERROR", request["sequence"], "motion_failed")
                    )
                else:
                    responses.append(encode_frame("DONE", request["sequence"]))
        return responses


def execute_fixed_step():
    motion_options = {"a": 5, "v": 5, "cp": 0}
    RelJointMovJ([1, 0, 0, 0, 0, 0], motion_options)
    Wait(1000)
    RelJointMovJ([-1, 0, 0, 0, 0, 0], motion_options)
    Wait(1)


def main():
    error, socket_id = TCPCreate(True, "192.168.5.1", 5200)
    if error:
        raise RuntimeError("tcp_create_failed")
    if api_failed(TCPStart(socket_id, 0)):
        raise RuntimeError("tcp_start_failed")
    session = DiagnosticSession(execute_fixed_step)
    while True:
        error, received = TCPRead(socket_id)
        if error:
            raise RuntimeError("tcp_read_failed")
        for response in session.feed(received):
            if api_failed(TCPWrite(socket_id, response)):
                raise RuntimeError("tcp_write_failed")


main()
