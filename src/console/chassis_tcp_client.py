"""Computer-side client for the non-motion RCP1/TCP chassis link."""

import socket

from chassis_tcp import MAX_SEQUENCE, MessageStreamDecoder, encode_message


EXPECTED_RESPONSES = {
    "HELLO": "WELCOME",
    "PING": "PONG",
    "STATUS": "STATE",
}


class ChassisTcpClientError(RuntimeError):
    """Describe a failed or rejected chassis TCP exchange."""


class ChassisTcpClient:
    """Perform one ordered, non-retrying request at a time."""

    def __init__(self, connection):
        self.connection = connection
        self.decoder = MessageStreamDecoder()
        self.next_sequence = 1
        self.last_response = None

    def _allocate_sequence(self):
        sequence = self.next_sequence
        self.next_sequence = 1 if sequence >= MAX_SEQUENCE else sequence + 1
        return sequence

    def _send_all(self, data):
        sent = 0
        while sent < len(data):
            count = self.connection.send(data[sent:])
            if not count:
                raise ChassisTcpClientError("connection_closed_during_write")
            sent += count

    def exchange(self, request_type, payload=None, ttl_ms=1000):
        if request_type not in EXPECTED_RESPONSES:
            raise ChassisTcpClientError("unsupported_non_motion_request")
        sequence = self._allocate_sequence()
        self._send_all(encode_message(request_type, sequence, ttl_ms, payload))
        while True:
            data = self.connection.recv(256)
            if not data:
                raise ChassisTcpClientError("connection_closed_before_response")
            messages, errors = self.decoder.feed(data)
            if errors:
                raise ChassisTcpClientError(errors[-1])
            for message in messages:
                if message["sequence"] != sequence:
                    raise ChassisTcpClientError("sequence_mismatch")
                if message["type"] == "ERROR":
                    raise ChassisTcpClientError(message["payload"]["code"])
                if message["type"] != EXPECTED_RESPONSES[request_type]:
                    raise ChassisTcpClientError("unexpected_response_type")
                self.last_response = message
                return message

    def probe(self, client_id="console", ttl_ms=1000):
        welcome = self.exchange("HELLO", {"client": client_id}, ttl_ms)
        pong = self.exchange("PING", {}, ttl_ms)
        state = self.exchange("STATUS", {}, ttl_ms)
        return {
            "ok": True,
            "state": state["payload"]["service"],
            "motion_enabled": state["payload"]["motion_enabled"],
            "sequences": [
                welcome["sequence"],
                pong["sequence"],
                state["sequence"],
            ],
            "responses": [welcome["type"], pong["type"], state["type"]],
        }


def open_connection(host, port=8765, timeout_seconds=3.0):
    """Open one bounded IPv4 TCP connection without retry."""
    if not isinstance(host, str) or not host.strip():
        raise ValueError("host is required")
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValueError("port must be in 1024..65535")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    return socket.create_connection((host.strip(), port), timeout_seconds)
