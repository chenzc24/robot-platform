"""RPA2 service hosted by the Dobot controller on LAN1."""

import math
import time

from motion_link import FrameStreamDecoder, MotionLinkError, decode_fields, encode_fields, encode_frame


MARKER = "RPA2"
PHYSICAL_JOINT_MIN = (-360.0, -135.0, -154.0, -160.0, -173.0, -360.0)
PHYSICAL_JOINT_MAX = (360.0, 135.0, 154.0, 160.0, 173.0, 360.0)
MAX_STROKE_SEGMENTS = 128


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


def _vector(value, length, code):
    values = value.split(",")
    if len(values) != length:
        raise ValueError(code)
    return tuple(_number(item, code) for item in values)


def _segments(value, code):
    if not isinstance(value, str) or not value:
        raise ValueError(code)
    values = value.split("/")
    if not 1 <= len(values) <= 8:
        raise ValueError(code)
    return tuple(_vector(item, 3, code) for item in values)


def _feedback_vector(value, container_name, component_names, code):
    """Normalize documented vectors plus common controller status wrappers."""
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], (int, bool)):
        if value[0]:
            raise ValueError(code)
        value = value[1]
    if isinstance(value, dict):
        if set(value) == {container_name}:
            value = value[container_name]
        elif set(value) == set(component_names):
            value = [value[name] for name in component_names]
        else:
            raise ValueError(code)
    if isinstance(value, dict):
        if set(value) != set(component_names):
            raise ValueError(code)
        value = [value[name] for name in component_names]
    if not isinstance(value, (list, tuple)) or len(value) != 6:
        raise ValueError(code)
    return tuple(_number(item, code) for item in value)


def _encode_vector(values):
    return ",".join("%.9g" % value for value in values)


class ArmSafetyPolicy:
    """Select default-deny production policy or unrestricted engineering mode."""

    def __init__(self, motion_enabled=False, joint_min=None, joint_max=None, pose_min=None, pose_max=None,
                 max_accel_pct=20, max_speed_pct=20, gripper_min_mm=0, gripper_max_mm=70,
                 yolo_mode=False):
        if not isinstance(yolo_mode, bool):
            raise ValueError("invalid_yolo_policy")
        self.yolo_mode = yolo_mode
        self.motion_enabled = motion_enabled is True
        self.joint_min = self._bounds(joint_min, "invalid_joint_policy")
        self.joint_max = self._bounds(joint_max, "invalid_joint_policy")
        self.pose_min = self._bounds(pose_min, "invalid_pose_policy")
        self.pose_max = self._bounds(pose_max, "invalid_pose_policy")
        self.max_accel_pct = self._policy_integer(max_accel_pct, 1, 100, "invalid_motion_policy")
        self.max_speed_pct = self._policy_integer(max_speed_pct, 1, 100, "invalid_motion_policy")
        self.gripper_min_mm = self._policy_integer(gripper_min_mm, 0, 70, "invalid_gripper_policy")
        self.gripper_max_mm = self._policy_integer(gripper_max_mm, 0, 70, "invalid_gripper_policy")
        if self.gripper_min_mm > self.gripper_max_mm:
            raise ValueError("invalid_gripper_policy")
        if self.motion_enabled and not self.yolo_mode:
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
        if not (self.motion_enabled or self.yolo_mode):
            raise ValueError("motion_disabled")

    def joint(self, joints, accel, speed):
        self._motion()
        if not self.yolo_mode and not self._inside(joints, self.joint_min, self.joint_max):
            raise ValueError("joint_out_of_policy")
        self.options(accel, speed)

    def pose(self, pose, accel, speed):
        self._motion()
        if not self.yolo_mode and not self._inside(pose, self.pose_min, self.pose_max):
            raise ValueError("pose_out_of_policy")
        self.options(accel, speed)

    def options(self, accel, speed):
        maximum_accel = 100 if self.yolo_mode else self.max_accel_pct
        maximum_speed = 100 if self.yolo_mode else self.max_speed_pct
        if not 1 <= accel <= maximum_accel:
            raise ValueError("acceleration_out_of_policy")
        if not 1 <= speed <= maximum_speed:
            raise ValueError("speed_out_of_policy")

    def relative(self, accel, speed):
        if not self.yolo_mode:
            raise ValueError("yolo_mode_required")
        self.options(accel, speed)

    def gripper(self, width):
        self._motion()
        if not self.gripper_min_mm <= width <= self.gripper_max_mm:
            raise ValueError("gripper_out_of_policy")

class DobotControllerApi:
    """Adapter for the controller-resident Python API exposed by pluginPy."""

    def __init__(self, check_movj, movj, check_movl, movl, set_parallel_gripper,
                 rel_joint_movj, rel_movl_user, get_angle, get_pose):
        functions = (check_movj, movj, check_movl, movl, set_parallel_gripper,
                     rel_joint_movj, rel_movl_user, get_angle, get_pose)
        if not all(callable(item) for item in functions):
            raise ValueError("controller_api_not_callable")
        self.check_movj, self.movj = check_movj, movj
        self.check_movl, self.movl = check_movl, movl
        self.set_parallel_gripper = set_parallel_gripper
        self.rel_joint_movj, self.rel_movl_user = rel_joint_movj, rel_movl_user
        self.get_angle, self.get_pose = get_angle, get_pose

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
        self.movj(point, options)

    def move_linear(self, pose, user, tool, accel, speed):
        point = {"pose": list(pose)}
        options = {"user": user, "tool": tool, "a": accel, "v": speed, "r": 0}
        if self._check_result(self.check_movl(point, options)) != 0:
            raise ValueError("linear_path_rejected")
        self.movl(point, options)

    def gripper(self, width):
        self.set_parallel_gripper(width)

    def jog_joint(self, joint_delta_deg, accel, speed):
        options = {"a": accel, "v": speed, "cp": 0}
        self.rel_joint_movj(list(joint_delta_deg), options)

    def jog_xyz(self, translation_mm, user, tool, accel, speed, blend=0):
        options = {"user": user, "tool": tool, "a": accel, "v": speed, "cp": blend}
        self.rel_movl_user(list(translation_mm) + [0, 0, 0], options)

    def draw_stroke(self, stroke):
        """Issue a complete lifted-to-lifted stroke inside the controller.

        The controller sees consecutive CP draw calls without a computer, UART,
        or RPA2 completion wait between them. The caller has already validated
        every vector and policy option before this method is entered.
        """
        self.jog_xyz(
            stroke["anchor_translation_mm"], stroke["user"], stroke["tool"],
            stroke["accel_pct"], stroke["travel_speed_pct"], 0,
        )
        self.jog_xyz(
            stroke["pen_down_translation_mm"], stroke["user"], stroke["tool"],
            stroke["accel_pct"], stroke["travel_speed_pct"], 0,
        )
        for segment in stroke["segments_mm"]:
            self.jog_xyz(
                segment, stroke["user"], stroke["tool"],
                stroke["accel_pct"], stroke["draw_speed_pct"],
                stroke["draw_blend_pct"],
            )
        self.jog_xyz(
            stroke["pen_up_translation_mm"], stroke["user"], stroke["tool"],
            stroke["accel_pct"], stroke["travel_speed_pct"], 0,
        )

    def read_feedback(self, user=0, tool=0):
        joints = _feedback_vector(
            self.get_angle(), "joint", ("j1", "j2", "j3", "j4", "j5", "j6"),
            "invalid_joint_feedback",
        )
        pose = _feedback_vector(
            self.get_pose(user, tool), "pose", ("x", "y", "z", "rx", "ry", "rz"),
            "invalid_pose_feedback",
        )
        return joints, pose


class ArmMotionService:
    """One synchronous primitive at a time. No cancellation is claimed."""

    def __init__(self, api, policy, clock_ms=None):
        self.api, self.policy = api, policy
        self.clock_ms = clock_ms or _clock_ms
        self.decoder = FrameStreamDecoder(MARKER)
        self.last_sequence, self.last_fingerprint, self.last_responses = 0, None, None
        self.service_state, self.error_code, self.active_sequence = "ready", None, None
        self.feedback_sample_id = 0
        self.stroke_queue = None

    def _response(self, request, kind, payload=""):
        return encode_frame(MARKER, kind, request["sequence"], 0, payload)

    def _error(self, request, code):
        self.error_code = code
        return (self._response(request, "ERROR", encode_fields((("error_code", code), ("retryable", 0)))),)

    def _state(self):
        self.feedback_sample_id = 1 if self.feedback_sample_id >= 2147483647 else self.feedback_sample_id + 1
        sample_time_ms = self.clock_ms()
        try:
            joints, pose = self.api.read_feedback(0, 0)
            feedback_valid, feedback_error = 1, "none"
            joint_text, pose_text = _encode_vector(joints), _encode_vector(pose)
        except ValueError as error:
            feedback_valid, feedback_error = 0, str(error)
            joint_text = pose_text = "unavailable"
        except Exception:
            feedback_valid, feedback_error = 0, "feedback_read_failed"
            joint_text = pose_text = "unavailable"
        return encode_fields((("service_state", self.service_state), ("motion_enabled", int(self.policy.motion_enabled or self.policy.yolo_mode)),
                              ("control_mode", "yolo" if self.policy.yolo_mode else "production"),
                              ("active_sequence", self.active_sequence or 0), ("last_error", self.error_code or "none"),
                              ("terminal_position_supported", 0), ("cancel_supported", 0),
                              ("feedback_valid", feedback_valid), ("feedback_error", feedback_error),
                              ("joint_deg", joint_text), ("pose", pose_text), ("pose_user", 0), ("pose_tool", 0),
                              ("sample_id", self.feedback_sample_id), ("sample_time_ms", sample_time_ms)))

    def _run(self, request, function, done_payload):
        self.service_state, self.active_sequence = "running", request["sequence"]
        replies = (self._response(request, "ACK"), self._response(request, "RUNNING"))
        try:
            function()
        except ValueError as error:
            self.service_state, self.active_sequence = "ready", None
            return replies + self._error(request, str(error))
        except RuntimeError as error:
            self.service_state, self.active_sequence = "fault", None
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
                joints, accel, speed = _vector(values["joint_deg"], 6, "invalid_joint"), _integer(values["accel_pct"], 1, 100, "invalid_acceleration"), _integer(values["speed_pct"], 1, 100, "invalid_speed")
                if values["blend_pct"] != "0": raise ValueError("blending_disabled")
                self.policy.joint(joints, accel, speed)
                return self._run(request, lambda: self.api.move_joint(joints, accel, speed), "primitive=move_joint;terminal_position=unknown")
            if kind == "MOVEL":
                values = decode_fields(request["payload"], ("pose", "user", "tool", "accel_pct", "speed_pct", "blend_mm"))
                pose = _vector(values["pose"], 6, "invalid_pose")
                user, tool = _integer(values["user"], 0, 9, "invalid_user"), _integer(values["tool"], 0, 9, "invalid_tool")
                accel, speed = _integer(values["accel_pct"], 1, 100, "invalid_acceleration"), _integer(values["speed_pct"], 1, 100, "invalid_speed")
                if values["blend_mm"] != "0": raise ValueError("blending_disabled")
                self.policy.pose(pose, accel, speed)
                return self._run(request, lambda: self.api.move_linear(pose, user, tool, accel, speed), "primitive=move_linear;terminal_position=unknown")
            if kind == "RELJOINT":
                values = decode_fields(request["payload"], ("joint_delta_deg", "accel_pct", "speed_pct", "blend_pct"))
                delta = _vector(values["joint_delta_deg"], 6, "invalid_joint_delta")
                accel = _integer(values["accel_pct"], 1, 100, "invalid_acceleration")
                speed = _integer(values["speed_pct"], 1, 100, "invalid_speed")
                if values["blend_pct"] != "0": raise ValueError("blending_disabled")
                self.policy.relative(accel, speed)
                return self._run(request, lambda: self.api.jog_joint(delta, accel, speed), "primitive=jog_joint;terminal_position=unknown")
            if kind == "RELLINEAR":
                try:
                    values = decode_fields(request["payload"], ("translation_mm", "user", "tool", "accel_pct", "speed_pct", "blend_pct"))
                    blend = _integer(values["blend_pct"], 0, 100, "invalid_blend")
                except MotionLinkError:
                    values = decode_fields(request["payload"], ("translation_mm", "user", "tool", "accel_pct", "speed_pct", "blend_mm"))
                    if values["blend_mm"] != "0": raise ValueError("blending_disabled")
                    blend = 0
                translation = _vector(values["translation_mm"], 3, "invalid_translation")
                user = _integer(values["user"], 0, 9, "invalid_user")
                tool = _integer(values["tool"], 0, 9, "invalid_tool")
                accel = _integer(values["accel_pct"], 1, 100, "invalid_acceleration")
                speed = _integer(values["speed_pct"], 1, 100, "invalid_speed")
                self.policy.relative(accel, speed)
                return self._run(request, lambda: self.api.jog_xyz(translation, user, tool, accel, speed, blend), "primitive=jog_xyz;blend_pct=%d;terminal_position=unknown" % blend)
            if kind == "STROKE_BEGIN":
                values = decode_fields(request["payload"], (
                    "anchor_translation_mm", "pen_down_translation_mm",
                    "pen_up_translation_mm", "user", "tool", "accel_pct",
                    "travel_speed_pct", "draw_speed_pct", "draw_blend_pct",
                ))
                stroke = {
                    "anchor_translation_mm": _vector(values["anchor_translation_mm"], 3, "invalid_stroke_vector"),
                    "pen_down_translation_mm": _vector(values["pen_down_translation_mm"], 3, "invalid_stroke_vector"),
                    "pen_up_translation_mm": _vector(values["pen_up_translation_mm"], 3, "invalid_stroke_vector"),
                    "user": _integer(values["user"], 0, 9, "invalid_user"),
                    "tool": _integer(values["tool"], 0, 9, "invalid_tool"),
                    "accel_pct": _integer(values["accel_pct"], 1, 100, "invalid_acceleration"),
                    "travel_speed_pct": _integer(values["travel_speed_pct"], 1, 100, "invalid_speed"),
                    "draw_speed_pct": _integer(values["draw_speed_pct"], 1, 100, "invalid_speed"),
                    "draw_blend_pct": _integer(values["draw_blend_pct"], 0, 100, "invalid_blend"),
                    "segments_mm": [],
                }
                self.policy.relative(stroke["accel_pct"], stroke["travel_speed_pct"])
                self.policy.relative(stroke["accel_pct"], stroke["draw_speed_pct"])
                # Replacing an unexecuted queue is safe: it has no controller
                # side effect and prevents stale segments surviving a restart.
                self.stroke_queue = stroke
                return self._run(request, lambda: None, "stroke_queue=ready")
            if kind == "STROKE_APPEND":
                values = decode_fields(request["payload"], ("segments_mm",))
                if self.stroke_queue is None:
                    raise ValueError("stroke_queue_not_started")
                segments = _segments(values["segments_mm"], "invalid_stroke_segments")
                if len(self.stroke_queue["segments_mm"]) + len(segments) > MAX_STROKE_SEGMENTS:
                    raise ValueError("stroke_queue_full")
                self.stroke_queue["segments_mm"].extend(segments)
                return self._run(request, lambda: None, "stroke_segments=%d" % len(self.stroke_queue["segments_mm"]))
            if kind == "STROKE_EXECUTE":
                decode_fields(request["payload"], ())
                if self.stroke_queue is None or not self.stroke_queue["segments_mm"]:
                    raise ValueError("stroke_queue_empty")
                stroke, self.stroke_queue = self.stroke_queue, None
                return self._run(
                    request, lambda: self.api.draw_stroke(stroke),
                    "primitive=draw_stroke;segments=%d;terminal_position=unknown" % len(stroke["segments_mm"]),
                )
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
