"""One-request RPA2 adapter for MaixCam UART0."""

import time

from motion_link import FrameStreamDecoder, MotionLinkError, decode_fields, encode_fields, encode_frame


class ArmMotionGatewayError(RuntimeError):
    def __init__(self, code):
        RuntimeError.__init__(self, code)
        self.code = code


class ArmMotionGateway:
    """Preserve response lifecycle and never retry a state-changing write."""

    def __init__(self, write, clock_ms=None, initial_sequence=1):
        if not callable(write):
            raise ValueError("write must be callable")
        if isinstance(initial_sequence, bool) or not isinstance(initial_sequence, int) or not 1 <= initial_sequence <= 2147483647:
            raise ValueError("invalid_initial_sequence")
        self.write = write
        self.clock_ms = clock_ms or (lambda: int(time.monotonic() * 1000))
        self.decoder = FrameStreamDecoder("RPA2")
        self.sequence, self.pending, self.state, self.error_code = initial_sequence, None, "idle", None

    def start(self, command, payload="", ttl_ms=1000):
        if self.pending is not None:
            raise ArmMotionGatewayError("request_in_flight")
        if not 100 <= ttl_ms <= 60000:
            raise ArmMotionGatewayError("invalid_ttl")
        sequence = self.sequence
        self.sequence = 1 if sequence >= 2147483647 else sequence + 1
        frame = encode_frame("RPA2", command, sequence, ttl_ms, payload)
        try:
            result = self.write(frame)
        except Exception:
            self.state, self.error_code = "fault", "uart_write_failed"
            raise ArmMotionGatewayError("uart_write_failed")
        if result is not None and result != len(frame):
            self.state, self.error_code = "fault", "uart_short_write"
            raise ArmMotionGatewayError("uart_short_write")
        self.pending = {"sequence": sequence, "command": command, "deadline": self.clock_ms() + ttl_ms,
                        "accepted": False, "motion": command not in ("PING", "STATUS")}
        self.state, self.error_code = "waiting", None
        return sequence

    def feed(self, data):
        frames, errors = self.decoder.feed(data)
        events = []
        for error in errors:
            self.error_code = error
        for frame in frames:
            if self.pending is None:
                # A safe request may have timed out locally while its UART reply is
                # still in flight. It has no computer command to complete now.
                continue
            if frame["sequence"] != self.pending["sequence"]:
                if frame["sequence"] < self.pending["sequence"]:
                    # UART ordering makes a lower response an expired request, not
                    # evidence against the newer in-flight request. Discard it.
                    events.append(("IGNORED", "stale_sequence", frame))
                    continue
                self.pending, self.state, self.error_code = None, "fault", "sequence_mismatch"
                events.append(("ERROR", "sequence_mismatch", frame))
                continue
            if frame["type"] == "ERROR":
                try:
                    code = decode_fields(frame["payload"], ("error_code", "retryable"))["error_code"]
                except MotionLinkError:
                    code = "invalid_error_payload"
                self.pending, self.state, self.error_code = None, "fault", code
                events.append(("ERROR", code, frame))
            elif frame["type"] in ("PONG", "STATE"):
                expected = "PONG" if self.pending["command"] == "PING" else "STATE"
                if frame["type"] != expected:
                    self.state, self.error_code = "fault", "invalid_lifecycle"
                    events.append(("ERROR", "invalid_lifecycle", frame))
                else:
                    self.pending, self.state, self.error_code = None, "ready", None
                    events.append(("DONE", None, frame))
            elif frame["type"] == "ACK" and not self.pending["accepted"]:
                self.pending["accepted"], self.state = True, "accepted"
                events.append(("ACK", None, frame))
            elif frame["type"] == "RUNNING" and self.pending["accepted"]:
                self.state = "running"
                events.append(("RUNNING", None, frame))
            elif frame["type"] == "DONE" and self.pending["accepted"]:
                self.pending, self.state, self.error_code = None, "ready", None
                events.append(("DONE", None, frame))
            else:
                self.pending, self.state, self.error_code = None, "fault", "invalid_lifecycle"
                events.append(("ERROR", "invalid_lifecycle", frame))
        return events

    def poll(self):
        if self.pending is None or self.clock_ms() <= self.pending["deadline"]:
            return None
        pending, self.pending = self.pending, None
        self.state = "unknown" if pending["motion"] else "fault"
        self.error_code = "response_timeout"
        return "UNKNOWN" if pending["motion"] else "FAULT"

    def snapshot(self):
        return {"state": self.state, "error_code": self.error_code,
                "pending_sequence": None if self.pending is None else self.pending["sequence"],
                "automatic_retry": False}


def arm_payload(name, payload):
    """Build the exact RPA2 field order; unexpected input fails before UART."""
    if name in ("arm.ping", "arm.status"):
        if payload: raise ArmMotionGatewayError("invalid_payload_fields")
        return ("PING" if name.endswith("ping") else "STATUS"), ""
    if name == "arm.l3_j1_cycle":
        if payload:
            raise ArmMotionGatewayError("invalid_payload_fields")
        return "L3J1CYCLE", ""
    if name == "arm.move_joint":
        if set(payload) != {"joint_deg", "accel_pct", "speed_pct"} or not isinstance(payload["joint_deg"], (list, tuple)) or len(payload["joint_deg"]) != 6:
            raise ArmMotionGatewayError("invalid_payload_fields")
        return "MOVEJ", encode_fields((("joint_deg", ",".join(str(item) for item in payload["joint_deg"])), ("accel_pct", payload["accel_pct"]), ("speed_pct", payload["speed_pct"]), ("blend_pct", 0)))
    if name == "arm.move_linear":
        if set(payload) != {"pose", "user", "tool", "accel_pct", "speed_pct"} or not isinstance(payload["pose"], (list, tuple)) or len(payload["pose"]) != 6:
            raise ArmMotionGatewayError("invalid_payload_fields")
        return "MOVEL", encode_fields((("pose", ",".join(str(item) for item in payload["pose"])), ("user", payload["user"]), ("tool", payload["tool"]), ("accel_pct", payload["accel_pct"]), ("speed_pct", payload["speed_pct"]), ("blend_mm", 0)))
    if name == "arm.gripper":
        if set(payload) != {"width_mm"}: raise ArmMotionGatewayError("invalid_payload_fields")
        return "GRIPPER", encode_fields((("width_mm", payload["width_mm"]),))
    raise ArmMotionGatewayError("unsupported_command")
