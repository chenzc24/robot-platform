"""Non-motion ESP32 responder for the computer-facing RCP1/TCP link."""

from chassis_tcp import MessageStreamDecoder, REQUEST_TYPES, encode_message


class ChassisTcpService:
    """Answer session, liveness, and status requests without motion hardware."""

    def __init__(self, transport):
        self.transport = transport
        self.decoder = MessageStreamDecoder()
        self.state = "safe_idle"
        self.error_code = None
        self.client_id = None
        self.requests_handled = 0
        self.last_sequence = None
        self._last_request = None
        self._last_response = None
        self._completed_types = set()

    @property
    def complete(self):
        return self._completed_types == {"HELLO", "PING", "STATUS"}

    def status_snapshot(self):
        return {
            "state": "ready" if self.complete else self.state,
            "error_code": self.error_code,
            "client_id": self.client_id,
            "requests_handled": self.requests_handled,
            "last_sequence": self.last_sequence,
            "motion_enabled": False,
            "complete": self.complete,
        }

    @staticmethod
    def _request_key(message):
        payload_items = tuple(sorted(message["payload"].items()))
        return (
            message["type"],
            message["sequence"],
            message["ttl_ms"],
            payload_items,
        )

    def _response_for(self, message):
        sequence = message["sequence"]
        message_type = message["type"]
        if message_type == "HELLO":
            if self.client_id is not None:
                return encode_message(
                    "ERROR", sequence, 0, {"code": "session_started"}
                )
            self.client_id = message["payload"]["client"]
            return encode_message(
                "WELCOME",
                sequence,
                0,
                {"service": "chassis", "motion_enabled": False},
            )
        if self.client_id is None:
            return encode_message(
                "ERROR", sequence, 0, {"code": "session_required"}
            )
        if message_type == "PING":
            return encode_message("PONG", sequence, 0, {"protocol": 1})
        if message_type == "STATUS":
            return encode_message(
                "STATE",
                sequence,
                0,
                {"service": "safe_idle", "motion_enabled": False},
            )
        return encode_message(
            "ERROR", sequence, 0, {"code": "unsupported_direction"}
        )

    def _write(self, response):
        written = self.transport.write(response)
        if written is not None and written != len(response):
            self.state = "fault"
            self.error_code = "tcp_short_write"
            raise OSError("TCP short write")

    def feed(self, data):
        messages, errors = self.decoder.feed(data)
        events = []
        if errors:
            self.error_code = errors[-1]
            events.extend(errors)
        for message in messages:
            request_key = self._request_key(message)
            if message["type"] not in REQUEST_TYPES:
                response = encode_message(
                    "ERROR",
                    message["sequence"],
                    0,
                    {"code": "unsupported_direction"},
                )
                self._write(response)
                self.error_code = "unsupported_direction"
                events.append("unsupported_direction")
                continue
            if self.last_sequence is not None and message["sequence"] <= self.last_sequence:
                if (
                    message["sequence"] == self.last_sequence
                    and request_key == self._last_request
                ):
                    self._write(self._last_response)
                    events.append("duplicate_replayed")
                else:
                    code = (
                        "sequence_conflict"
                        if message["sequence"] == self.last_sequence
                        else "out_of_order"
                    )
                    response = encode_message(
                        "ERROR", message["sequence"], 0, {"code": code}
                    )
                    self._write(response)
                    self.error_code = code
                    events.append(code)
                continue
            response_error = None
            if message["type"] == "HELLO" and self.client_id is not None:
                response_error = "session_started"
            elif message["type"] != "HELLO" and self.client_id is None:
                response_error = "session_required"
            response = self._response_for(message)
            self._write(response)
            self._last_request = request_key
            self._last_response = response
            self.last_sequence = message["sequence"]
            if response_error is not None:
                self.error_code = response_error
                events.append(response_error)
                continue
            self.requests_handled += 1
            self._completed_types.add(message["type"])
            self.error_code = None
            events.append("response_sent")
        return events
