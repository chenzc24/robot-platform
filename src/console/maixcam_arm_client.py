"""Non-retrying computer client for the MaixCam arm NDJSON endpoint."""

import socket
import time
import math

from control_envelope import EnvelopeStreamDecoder, encode_message


QUERY_TTL_MS = 5000
RESPONSE_MARGIN_SECONDS = 1.0
STROKE_APPEND_SEGMENT_LIMIT = 8
STROKE_SEGMENT_LIMIT = 128


class MaixCamArmClientError(RuntimeError):
    def __init__(self, code):
        RuntimeError.__init__(self, code)
        self.code = code


class MaixCamArmUnknown(MaixCamArmClientError):
    pass


class MaixCamArmClient:
    def __init__(self, connection, session_id="console"):
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("session_id is required")
        self.connection, self.session_id = connection, session_id
        self.decoder, self.sequence, self._pending = EnvelopeStreamDecoder(), 1, []

    def _remaining_timeout(self, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("arm_response_deadline")
        setter = getattr(self.connection, "settimeout", None)
        if callable(setter):
            setter(remaining)

    def _send_all(self, data, deadline):
        sent = 0
        while sent < len(data):
            self._remaining_timeout(deadline)
            count = self.connection.send(data[sent:])
            if not count: raise MaixCamArmClientError("connection_closed_during_write")
            sent += count

    def _next(self, deadline):
        while not self._pending:
            self._remaining_timeout(deadline)
            data = self.connection.recv(4096)
            if not data: raise MaixCamArmClientError("connection_closed_before_response")
            messages, errors = self.decoder.feed(data)
            if errors: raise MaixCamArmClientError(errors[-1])
            self._pending.extend(messages)
        return self._pending.pop(0)

    def command(self, name, payload=None, ttl_ms=QUERY_TTL_MS):
        sequence = self.sequence
        self.sequence = None if sequence >= 2147483647 else sequence + 1
        if sequence is None: raise MaixCamArmClientError("sequence_exhausted")
        message_id = "%s-%d" % (self.session_id, sequence)
        command = {"version": 1, "kind": "command", "message_id": message_id, "sequence": sequence,
                   "target": "arm", "name": name, "ttl_ms": ttl_ms, "payload": payload or {}}
        state_changing = name in (
            "arm.move_joint", "arm.move_linear", "arm.jog_joint", "arm.jog_xyz",
            "arm.gripper", "arm.stroke_execute",
        )
        get_timeout = getattr(self.connection, "gettimeout", None)
        set_timeout = getattr(self.connection, "settimeout", None)
        restore_timeout = callable(get_timeout) and callable(set_timeout)
        original_timeout = get_timeout() if restore_timeout else None
        try:
            data = encode_message(command)
            deadline = time.monotonic() + ttl_ms / 1000.0 + RESPONSE_MARGIN_SECONDS
            self._send_all(data, deadline)
            states = []
            while True:
                response = self._next(deadline)
                if response.get("kind") != "lifecycle" or response.get("correlation_id") != message_id:
                    raise MaixCamArmClientError("unexpected_response")
                states.append(response)
                lifecycle = response["lifecycle"]
                if lifecycle in ("DONE", "REJECTED", "FAULT"):
                    return states
                if lifecycle == "UNKNOWN":
                    raise MaixCamArmUnknown("outcome_unknown")
        except MaixCamArmUnknown:
            raise
        except Exception as error:
            if state_changing: raise MaixCamArmUnknown("outcome_unknown") from error
            raise
        finally:
            if restore_timeout:
                try:
                    set_timeout(original_timeout)
                except OSError:
                    pass

    def ping(self, ttl_ms=QUERY_TTL_MS): return self.command("arm.ping", {}, ttl_ms)
    def status(self, ttl_ms=QUERY_TTL_MS): return self.command("arm.status", {}, ttl_ms)
    def move_joint(self, joint_deg, accel_pct=5, speed_pct=5, ttl_ms=60000):
        return self.command("arm.move_joint", {"joint_deg": list(joint_deg), "accel_pct": accel_pct, "speed_pct": speed_pct}, ttl_ms)
    def move_linear(self, pose, user=0, tool=0, accel_pct=5, speed_pct=5, ttl_ms=60000):
        return self.command("arm.move_linear", {"pose": list(pose), "user": user, "tool": tool, "accel_pct": accel_pct, "speed_pct": speed_pct}, ttl_ms)
    def jog_joint(self, joint_delta_deg, accel_pct=5, speed_pct=5, ttl_ms=60000):
        return self.command("arm.jog_joint", {"joint_delta_deg": list(joint_delta_deg), "accel_pct": accel_pct, "speed_pct": speed_pct}, ttl_ms)
    def jog_xyz(self, translation_mm, user=0, tool=0, accel_pct=5, speed_pct=5, ttl_ms=60000, blend_pct=0):
        return self.command("arm.jog_xyz", {"translation_mm": list(translation_mm), "user": user, "tool": tool, "accel_pct": accel_pct, "speed_pct": speed_pct, "blend_pct": blend_pct}, ttl_ms)
    def gripper(self, width_mm, ttl_ms=60000):
        if (
            isinstance(width_mm, bool)
            or not isinstance(width_mm, (int, float))
            or int(width_mm) != width_mm
        ):
            raise ValueError("invalid_gripper_width")
        return self.command("arm.gripper", {"width_mm": int(width_mm)}, ttl_ms)

    @staticmethod
    def _stroke_vector(value, name):
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            raise ValueError("invalid_%s" % name)
        result = []
        for item in value:
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
                raise ValueError("invalid_%s" % name)
            result.append(float(item))
        return result

    def draw_stroke(
        self, anchor_translation_mm, pen_down_translation_mm,
        pen_up_translation_mm, segments_mm, user=0, tool=0, accel_pct=5,
        travel_speed_pct=5, draw_speed_pct=5, draw_blend_pct=100,
        ttl_ms=60000,
    ):
        """Stage one bounded stroke, then execute it as one controller action."""
        if not isinstance(segments_mm, (list, tuple)) or not 1 <= len(segments_mm) <= STROKE_SEGMENT_LIMIT:
            raise ValueError("invalid_stroke_segments")
        segments = [self._stroke_vector(value, "stroke_segment") for value in segments_mm]
        self.command("arm.stroke_begin", {
            "anchor_translation_mm": self._stroke_vector(anchor_translation_mm, "stroke_anchor"),
            "pen_down_translation_mm": self._stroke_vector(pen_down_translation_mm, "pen_down"),
            "pen_up_translation_mm": self._stroke_vector(pen_up_translation_mm, "pen_up"),
            "user": user, "tool": tool, "accel_pct": accel_pct,
            "travel_speed_pct": travel_speed_pct,
            "draw_speed_pct": draw_speed_pct,
            "draw_blend_pct": draw_blend_pct,
        }, ttl_ms)
        for index in range(0, len(segments), STROKE_APPEND_SEGMENT_LIMIT):
            self.command("arm.stroke_append", {
                "segments_mm": segments[index:index + STROKE_APPEND_SEGMENT_LIMIT],
            }, ttl_ms)
        return self.command("arm.stroke_execute", {}, ttl_ms)


def open_connection(host, port, timeout_seconds=3):
    if not isinstance(host, str) or not host.strip() or isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValueError("invalid connection settings")
    return socket.create_connection((host.strip(), port), timeout_seconds)
