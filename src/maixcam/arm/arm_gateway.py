"""Fail-closed gateway for ping and one fixed arm validation step."""

import time

from link_protocol import FrameStreamDecoder, MAX_SEQUENCE, encode_frame


class ArmGatewayError(RuntimeError):
    """Expose a stable gateway error code."""

    def __init__(self, code):
        RuntimeError.__init__(self, code)
        self.code = code


class ArmDiagnosticGateway:
    """Track one in-flight request and one fixed validation step."""

    def __init__(self, write, timeout_seconds=1.0, clock=None):
        if not callable(write):
            raise ValueError("write must be callable")
        if timeout_seconds < 0.1 or timeout_seconds > 30.0:
            raise ValueError("timeout is outside the diagnostic range")
        self._write = write
        self._timeout_seconds = timeout_seconds
        self._clock = clock or time.monotonic
        self._decoder = FrameStreamDecoder()
        self._next_sequence = 1
        self._pending_sequence = None
        self._expected_response = None
        self._sent_at = None
        self._step_consumed = False
        self.state = "idle"
        self.error_code = None
        self.round_trip_ms = None

    @property
    def pending_sequence(self):
        return self._pending_sequence

    def request(self, command):
        if command == "ping":
            return self.request_ping()
        if command == "fixed_j1_step":
            return self.request_fixed_step()
        else:
            self.state = "safe_idle"
            self.error_code = "motion_disabled"
            raise ArmGatewayError("motion_disabled")

    def request_ping(self):
        return self._request("PING", "PONG")

    def request_fixed_step(self):
        if self._step_consumed:
            raise ArmGatewayError("motion_already_consumed")
        self._step_consumed = True
        return self._request("STEP", "DONE")

    def _request(self, request_type, response_type):
        if self._pending_sequence is not None:
            raise ArmGatewayError("request_in_flight")
        sequence = self._next_sequence
        self._next_sequence = 1 if sequence == MAX_SEQUENCE else sequence + 1
        frame = encode_frame(request_type, sequence)
        try:
            written = self._write(frame)
        except Exception:
            self.state = "fault"
            self.error_code = "transport_write_failed"
            raise ArmGatewayError("transport_write_failed")
        if written is not None and written != len(frame):
            self.state = "fault"
            self.error_code = "short_write"
            raise ArmGatewayError("short_write")
        self._pending_sequence = sequence
        self._expected_response = response_type
        self._sent_at = self._clock()
        self.state = "waiting"
        self.error_code = None
        return sequence

    def feed(self, data):
        frames, errors = self._decoder.feed(data)
        if errors:
            self.state = "fault"
            self.error_code = errors[-1]
        for frame in frames:
            if frame["type"] == "ERROR":
                if (
                    self._pending_sequence is not None
                    and frame["sequence"] != self._pending_sequence
                ):
                    self.state = "fault"
                    self.error_code = "sequence_mismatch"
                    continue
                self.state = "fault"
                self.error_code = frame["payload"]
                self._pending_sequence = None
                self._expected_response = None
                self._sent_at = None
                continue
            if frame["type"] != self._expected_response:
                self.state = "fault"
                self.error_code = "unexpected_response"
                continue
            if self._pending_sequence is None:
                self.state = "fault"
                self.error_code = "unsolicited_response"
                continue
            if frame["sequence"] != self._pending_sequence:
                self.state = "fault"
                self.error_code = "sequence_mismatch"
                continue
            self.round_trip_ms = int((self._clock() - self._sent_at) * 1000)
            self._pending_sequence = None
            self._expected_response = None
            self._sent_at = None
            self.state = "ready"
            self.error_code = None
            return True
        return False

    def poll(self):
        if self._pending_sequence is None:
            return False
        if self._clock() - self._sent_at < self._timeout_seconds:
            return False
        self._pending_sequence = None
        self._expected_response = None
        self._sent_at = None
        self.state = "disconnected"
        self.error_code = "response_timeout"
        return True

    def snapshot(self):
        return {
            "state": self.state,
            "error_code": self.error_code,
            "pending_sequence": self._pending_sequence,
            "round_trip_ms": self.round_trip_ms,
            "motion_enabled": False,
            "fixed_step_consumed": self._step_consumed,
        }
