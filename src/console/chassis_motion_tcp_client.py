"""Computer-side non-retrying client for lease-free RCP/TCP v3 control."""

import socket

from chassis_tcp_v3 import (
    CONTROL_TYPES,
    MAX_SEQUENCE,
    MessageStreamDecoder,
    encode_message,
)


class ChassisMotionTcpClientError(RuntimeError):
    """Base error for a locally rejected or invalid v3 exchange."""

    def __init__(self, code):
        RuntimeError.__init__(self, code)
        self.code = code


class ChassisMotionTcpRejected(ChassisMotionTcpClientError):
    """The ESP32 explicitly rejected a request before successful completion."""

    explicit_rejection = True


class ChassisMotionTcpUnknown(ChassisMotionTcpClientError):
    """A state-changing request lost evidence of its terminal outcome."""


class ChassisMotionTcpClient:
    """Hold the single authenticated ESP32 connection and serialize requests."""

    def __init__(self, connection):
        self.connection = connection
        self.decoder = MessageStreamDecoder()
        self.next_sequence = 1
        self._pending_messages = []
        self.authenticated = False
        self.last_response = None

    def _allocate_sequence(self):
        if self.next_sequence is None:
            raise ChassisMotionTcpClientError("sequence_exhausted")
        sequence = self.next_sequence
        self.next_sequence = None if sequence >= MAX_SEQUENCE else sequence + 1
        return sequence

    def _send_all(self, data):
        sent = 0
        while sent < len(data):
            count = self.connection.send(data[sent:])
            if not count:
                raise ChassisMotionTcpClientError("connection_closed_during_write")
            sent += count

    def _next_message(self):
        while True:
            if self._pending_messages:
                return self._pending_messages.pop(0)
            data = self.connection.recv(512)
            if not data:
                raise ChassisMotionTcpClientError("connection_closed_before_response")
            messages, errors = self.decoder.feed(data)
            if errors:
                raise ChassisMotionTcpClientError(errors[-1])
            if messages:
                self._pending_messages.extend(messages[1:])
                return messages[0]

    @staticmethod
    def _query_response(request_type):
        return {
            "HELLO": "WELCOME",
            "PING": "PONG",
            "STATUS": "STATE",
            "LINE_FOLLOW_STATUS": "LINE_FOLLOW_STATE",
        }.get(request_type)

    def _receive_terminal(self, request_type, sequence):
        expected_query = self._query_response(request_type)
        seen_ack = False
        while True:
            message = self._next_message()
            if message["sequence"] != sequence:
                raise ChassisMotionTcpClientError("sequence_mismatch")
            if message["type"] == "ERROR":
                raise ChassisMotionTcpRejected(message["payload"]["code"])
            if expected_query is not None:
                if message["type"] != expected_query:
                    raise ChassisMotionTcpClientError("unexpected_response_type")
                self.last_response = message
                return message
            if message["type"] == "ACK":
                if seen_ack or message["payload"]["command"] != request_type:
                    raise ChassisMotionTcpClientError("invalid_lifecycle")
                seen_ack = True
                continue
            if message["type"] == "DONE":
                if not seen_ack or message["payload"]["command"] != request_type:
                    raise ChassisMotionTcpClientError("invalid_lifecycle")
                self.last_response = message
                return message
            raise ChassisMotionTcpClientError("invalid_lifecycle")

    def exchange(self, request_type, payload=None, ttl_ms=1000):
        sequence = self._allocate_sequence()
        frame = encode_message(request_type, sequence, ttl_ms, payload)
        state_changing = request_type in CONTROL_TYPES
        try:
            self._send_all(frame)
            return self._receive_terminal(request_type, sequence)
        except ChassisMotionTcpRejected:
            raise
        except ChassisMotionTcpUnknown:
            raise
        except Exception as error:
            if state_changing:
                raise ChassisMotionTcpUnknown("outcome_unknown") from error
            raise

    def hello(self, client_id, ttl_ms=1000):
        response = self.exchange(
            "HELLO",
            {"client": client_id},
            ttl_ms,
        )
        self.authenticated = True
        return response

    def ping(self, ttl_ms=1000):
        return self.exchange("PING", {}, ttl_ms)

    def status(self, ttl_ms=1000):
        return self.exchange("STATUS", {}, ttl_ms)

    def enable(self, ttl_ms=1000):
        return self.exchange("ENABLE", {}, ttl_ms)

    def velocity(
        self,
        vx_mm_s,
        vy_mm_s,
        omega_mrad_s,
        hold_ms=250,
        ttl_ms=500,
    ):
        return self.exchange(
            "VELOCITY",
            {
                "vx_mm_s": vx_mm_s,
                "vy_mm_s": vy_mm_s,
                "omega_mrad_s": omega_mrad_s,
                "hold_ms": hold_ms,
            },
            ttl_ms,
        )

    def line_follow_start(self, direction, ttl_ms=1000):
        return self.exchange(
            "LINE_FOLLOW_START", {"direction": direction}, ttl_ms
        )

    def line_follow_status(self, ttl_ms=1000):
        return self.exchange("LINE_FOLLOW_STATUS", {}, ttl_ms)

    def line_follow_stop(self, ttl_ms=1000):
        return self.exchange("LINE_FOLLOW_STOP", {}, ttl_ms)

    def stop(self, ttl_ms=1000):
        return self.exchange("STOP", {}, ttl_ms)

    def disable(self, ttl_ms=1000):
        return self.exchange("DISABLE", {}, ttl_ms)


def open_connection(host, port, timeout_seconds=3.0):
    """Open one bounded IPv4 TCP connection without retry."""
    if not isinstance(host, str) or not host.strip():
        raise ValueError("host is required")
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValueError("port must be in 1024..65535")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    return socket.create_connection((host.strip(), port), timeout_seconds)
