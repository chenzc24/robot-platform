"""Non-retrying computer client for the MaixCam arm NDJSON endpoint."""

import socket

from control_envelope import EnvelopeStreamDecoder, encode_message


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

    def _send_all(self, data):
        sent = 0
        while sent < len(data):
            count = self.connection.send(data[sent:])
            if not count: raise MaixCamArmClientError("connection_closed_during_write")
            sent += count

    def _next(self):
        while not self._pending:
            data = self.connection.recv(4096)
            if not data: raise MaixCamArmClientError("connection_closed_before_response")
            messages, errors = self.decoder.feed(data)
            if errors: raise MaixCamArmClientError(errors[-1])
            self._pending.extend(messages)
        return self._pending.pop(0)

    def command(self, name, payload=None, ttl_ms=1000):
        sequence = self.sequence
        self.sequence = None if sequence >= 2147483647 else sequence + 1
        if sequence is None: raise MaixCamArmClientError("sequence_exhausted")
        message_id = "%s-%d" % (self.session_id, sequence)
        command = {"version": 1, "kind": "command", "message_id": message_id, "sequence": sequence,
                   "target": "arm", "name": name, "ttl_ms": ttl_ms, "payload": payload or {}}
        state_changing = name in ("arm.move_joint", "arm.move_linear", "arm.jog_joint", "arm.jog_xyz", "arm.gripper")
        try:
            self._send_all(encode_message(command))
            states = []
            while True:
                response = self._next()
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

    def ping(self, ttl_ms=1000): return self.command("arm.ping", {}, ttl_ms)
    def status(self, ttl_ms=1000): return self.command("arm.status", {}, ttl_ms)
    def move_joint(self, joint_deg, accel_pct=5, speed_pct=5, ttl_ms=60000):
        return self.command("arm.move_joint", {"joint_deg": list(joint_deg), "accel_pct": accel_pct, "speed_pct": speed_pct}, ttl_ms)
    def move_linear(self, pose, user=0, tool=0, accel_pct=5, speed_pct=5, ttl_ms=60000):
        return self.command("arm.move_linear", {"pose": list(pose), "user": user, "tool": tool, "accel_pct": accel_pct, "speed_pct": speed_pct}, ttl_ms)
    def jog_joint(self, joint_delta_deg, accel_pct=5, speed_pct=5, ttl_ms=60000):
        return self.command("arm.jog_joint", {"joint_delta_deg": list(joint_delta_deg), "accel_pct": accel_pct, "speed_pct": speed_pct}, ttl_ms)
    def jog_xyz(self, translation_mm, user=0, tool=0, accel_pct=5, speed_pct=5, ttl_ms=60000):
        return self.command("arm.jog_xyz", {"translation_mm": list(translation_mm), "user": user, "tool": tool, "accel_pct": accel_pct, "speed_pct": speed_pct}, ttl_ms)
    def gripper(self, width_mm, ttl_ms=2000): return self.command("arm.gripper", {"width_mm": width_mm}, ttl_ms)


def open_connection(host, port, timeout_seconds=3):
    if not isinstance(host, str) or not host.strip() or isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValueError("invalid connection settings")
    return socket.create_connection((host.strip(), port), timeout_seconds)
