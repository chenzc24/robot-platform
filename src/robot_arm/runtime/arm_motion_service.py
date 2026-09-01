"""Default-deny RPA2 service hosted by the Dobot controller on LAN1."""

import math
import time

from motion_link import FrameStreamDecoder, MotionLinkError, decode_fields, encode_fields, encode_frame


MARKER = "RPA2"
PHYSICAL_JOINT_MIN = (-360.0, -135.0, -154.0, -160.0, -173.0, -360.0)
PHYSICAL_JOINT_MAX = (360.0, 135.0, 154.0, 160.0, 173.0, 360.0)


def _clock_ms():
    return int((time.monotonic() if hasattr(time, "monotonic") else time.time()) * 1000)


def _number(value, code):
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValueError(code)
    if not math.isfinite(result):
        raise ValueError(code)
    return result


def _integer(value, low, high, code):
    if not isinstance(value, str) or not value.isdigit() or not low <= int(value) <= high:
        raise ValueError(code)
    return int(value)


def _vector(value, code):
    values = value.split(",")
    if len(values) != 6:
        raise ValueError(code)
    return tuple(_number(item, code) for item in values)


def _api_failed(result):
    if result is None:
        return False
    if isinstance(result, tuple):
        return bool(result[0]) if result else False
    return bool(result)


class ArmSafetyPolicy:
    """A deliberately incomplete local policy blocks every motion command."""

    def __init__(self, motion_enabled=False, joint_min=None, joint_max=None, pose_min=None, pose_max=None,
                 max_accel_pct=20, max_speed_pct=20, gripper_min_mm=0, gripper_max_mm=70):
        self.motion_enabled = motion_enabled is True
        self.joint_min = self._bounds(joint_min, "invalid_joint_policy")
        self.joint_max = self._bounds(joint_max, "invalid_joint_policy")
        self.pose_min = self._bounds(pose_min, "invalid_pose_policy")
        self.pose_max = self._bounds(pose_max, "invalid_pose_policy")
        self.max_accel_pct = self._policy_integer(max_accel_pct, 1, 20, "invalid_motion_policy")
        self.max_speed_pct = self._policy_integer(max_speed_pct, 1, 20, "invalid_motion_policy")
        self.gripper_min_mm = self._policy_integer(gripper_min_mm, 0, 70, "invalid_gripper_policy")
        self.gripper_max_mm = self._policy_integer(gripper_max_mm, 0, 70, "invalid_gripper_policy")
        if self.gripper_min_mm > self.gripper_max_mm:
            raise ValueError("invalid_gripper_policy")
        if self.motion_enabled:
            if None in (self.joint_min, self.joint_max, self.pose_min, self.pose_max):
                raise ValueError("motion_policy_requires_bounds")
            self._ordered(self.joint_min, self.joint_max, "invalid_joint_policy")
            self._ordered(self.pose_min, self.pose_max, "invalid_pose_policy")
            if not self._inside(self.joint_min, PHYSICAL_JOINT_MIN, PHYSICAL_JOINT_MAX) or not self._inside(self.joint_max, PHYSICAL_JOINT_MIN, PHYSICAL_JOINT_MAX):
                raise ValueError("joint_policy_exceeds_physical_limit")

    @staticmethod
    def _bounds(value, code):
        if value is None:
            return None
        if not isinstance(value, (list, tuple)) or len(value) != 6:
            raise ValueError(code)
        return tuple(_number(item, code) for item in value)

    @staticmethod
    def _policy_integer(value, low, high, code):
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(code)
        return value

    @staticmethod
    def _inside(value, low, high):
        return all(low_item <= item <= high_item for item, low_item, high_item in zip(value, low, high))

    @staticmethod
    def _ordered(low, high, code):
        if any(left > right for left, right in zip(low, high)):
            raise ValueError(code)

    def _motion(self):
        if not self.motion_enabled:
            raise ValueError("motion_disabled")

    def joint(self, joints, accel, speed):
        self._motion()
        if not self._inside(joints, self.joint_min, self.joint_max):
            raise ValueError("joint_out_of_policy")
        self.options(accel, speed)

    def pose(self, pose, accel, speed):
        self._motion()
        if not self._inside(pose, self.pose_min, self.pose_max):
            raise ValueError("pose_out_of_policy")
        self.options(accel, speed)

    def options(self, accel, speed):
        if not 1 <= accel <= self.max_accel_pct:
            raise ValueError("acceleration_out_of_policy")
        if not 1 <= speed <= self.max_speed_pct:
            raise ValueError("speed_out_of_policy")

    def gripper(self, width):
        self._motion()
        if not self.gripper_min_mm <= width <= self.gripper_max_mm:
            raise ValueError("gripper_out_of_policy")


class DobotControllerApi:
    """Narrow adapter. Its API-return terminal is explicitly not physical proof."""

    def __init__(self, check_movj, movj, check_movl, movl, set_parallel_gripper):
        if not all(callable(item) for item in (check_movj, movj, check_movl, movl, set_parallel_gripper)):
            raise ValueError("controller_api_not_callable")
        self.check_movj, self.movj = check_movj, movj
        self.check_movl, self.movl = check_movl, movl
        self.set_parallel_gripper = set_parallel_gripper

    @staticmethod
    def _check_result(value):
        value = value[0] if isinstance(value, tuple) and value else value
        if isinstance(value, bool) or not isinstance(value, int):
            return -1
        return value

    def move_joint(self, joints, accel, speed):
        point, options = {"joint": list(joints)}, {"a": accel, "v": speed, "cp": 0}
        if self._check_result(self.check_movj(point, options)) != 0:
            raise ValueError("joint_path_rejected")
        if _api_failed(self.movj(point, options)):
            raise RuntimeError("movj_failed")

    def move_linear(self, pose, user, tool, accel, speed):
        point = {"pose": list(pose)}
        options = {"user": user, "tool": tool, "a": accel, "v": speed, "r": 0}
        if self._check_result(self.check_movl(point, options)) != 0:
            raise ValueError("linear_path_rejected")
        if _api_failed(self.movl(point, options)):
            raise RuntimeError("movl_failed")

    def gripper(self, width):
        if _api_failed(self.set_parallel_gripper(width)):
            raise RuntimeError("gripper_failed")


class ArmMotionService:
    """One synchronous primitive at a time. No cancellation is claimed."""

    def __init__(self, api, policy, clock_ms=None):
        self.api, self.policy = api, policy
        self.clock_ms = clock_ms or _clock_ms
        self.decoder = FrameStreamDecoder(MARKER)
        self.last_sequence, self.last_fingerprint, self.last_responses = 0, None, None
        self.service_state, self.error_code, self.active_sequence = "ready", None, None

    def _response(self, request, kind, payload=""):
        return encode_frame(MARKER, kind, request["sequence"], 0, payload)

    def _error(self, request, code):
        self.error_code = code
        return (self._response(request, "ERROR", encode_fields((("error_code", code), ("retryable", 0)))),)

    def _state(self):
        return encode_fields((("service_state", self.service_state), ("motion_enabled", int(self.policy.motion_enabled)),
                              ("active_sequence", self.active_sequence or 0), ("last_error", self.error_code or "none"),
                              ("terminal_position_supported", 0), ("cancel_supported", 0)))

    def _run(self, request, function, done_payload):
        self.service_state, self.active_sequence = "running", request["sequence"]
        replies = (self._response(request, "ACK"), self._response(request, "RUNNING"))
        try:
            function()
        except ValueError as error:
            self.service_state, self.active_sequence = "ready", None
            return replies + self._error(request, str(error))
        except Exception:
            self.service_state, self.active_sequence = "fault", None
            return replies + self._error(request, "execution_failed")
        self.service_state, self.active_sequence, self.error_code = "ready", None, None
        return replies + (self._response(request, "DONE", done_payload),)

    def _execute(self, request, received, now):
        try:
            if now > received + request["ttl_ms"]:
                return self._error(request, "expired")
            kind = request["type"]
            if kind == "PING":
                decode_fields(request["payload"], ())
                return (self._response(request, "PONG", "protocol=2"),)
            if kind == "STATUS":
                decode_fields(request["payload"], ())
                return (self._response(request, "STATE", self._state()),)
            if self.service_state == "fault":
                return self._error(request, "service_fault")
            if kind == "MOVEJ":
                values = decode_fields(request["payload"], ("joint_deg", "accel_pct", "speed_pct", "blend_pct"))
                joints, accel, speed = _vector(values["joint_deg"], "invalid_joint"), _integer(values["accel_pct"], 1, 100, "invalid_acceleration"), _integer(values["speed_pct"], 1, 100, "invalid_speed")
                if values["blend_pct"] != "0": raise ValueError("blending_disabled")
                self.policy.joint(joints, accel, speed)
                return self._run(request, lambda: self.api.move_joint(joints, accel, speed), "primitive=move_joint;terminal_position=unknown")
            if kind == "MOVEL":
                values = decode_fields(request["payload"], ("pose", "user", "tool", "accel_pct", "speed_pct", "blend_mm"))
                pose = _vector(values["pose"], "invalid_pose")
                user, tool = _integer(values["user"], 0, 9, "invalid_user"), _integer(values["tool"], 0, 9, "invalid_tool")
                accel, speed = _integer(values["accel_pct"], 1, 100, "invalid_acceleration"), _integer(values["speed_pct"], 1, 100, "invalid_speed")
                if values["blend_mm"] != "0": raise ValueError("blending_disabled")
                self.policy.pose(pose, accel, speed)
                return self._run(request, lambda: self.api.move_linear(pose, user, tool, accel, speed), "primitive=move_linear;terminal_position=unknown")
            if kind == "GRIPPER":
                values = decode_fields(request["payload"], ("width_mm",))
                width = _integer(values["width_mm"], 0, 70, "invalid_gripper")
                self.policy.gripper(width)
                return self._run(request, lambda: self.api.gripper(width), "width_mm=%d;terminal_position=unknown" % width)
            return self._error(request, "unsupported_command")
        except (MotionLinkError, ValueError) as error:
            return self._error(request, getattr(error, "code", str(error)))

    def handle_message(self, request, received_at_ms=None, now_ms=None):
        now, received = self.clock_ms() if now_ms is None else now_ms, self.clock_ms() if received_at_ms is None else received_at_ms
        fingerprint = encode_frame(MARKER, request["type"], request["sequence"], request["ttl_ms"], request["payload"])
        if request["sequence"] == self.last_sequence:
            return self.last_responses if fingerprint == self.last_fingerprint else self._error(request, "sequence_conflict")
        if request["sequence"] < self.last_sequence:
            return self._error(request, "sequence_replay")
        replies = self._execute(request, received, now)
        self.last_sequence, self.last_fingerprint, self.last_responses = request["sequence"], fingerprint, replies
        return replies

    def feed(self, data, received_at_ms=None, now_ms=None):
        frames, errors = self.decoder.feed(data)
        replies = []
        for frame in frames:
            replies.extend(self.handle_message(frame, received_at_ms, now_ms))
        return tuple(replies), errors
