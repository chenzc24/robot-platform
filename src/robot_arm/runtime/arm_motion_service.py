"""RPA2 service hosted by the Dobot controller on LAN1."""

import math
import time

from motion_link import FrameStreamDecoder, MotionLinkError, decode_fields, encode_fields, encode_frame
from arm_faults import ArmFault, ControllerFaultAccess, controller_state_payload, fault_record, fault_payload


MARKER = "RPA2"
PHYSICAL_JOINT_MIN = (-360.0, -135.0, -154.0, -160.0, -173.0, -360.0)
PHYSICAL_JOINT_MAX = (360.0, 135.0, 154.0, 160.0, 173.0, 360.0)


def _clock_ms():
    return int((time.monotonic() if hasattr(time, "monotonic") else time.time()) * 1000)


def _number(value, code):
    if isinstance(value, bool):
        raise ValueError(code)
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
                 rel_joint_movj, rel_movl_user, get_angle, get_pose, fault_access=None):
        functions = (check_movj, movj, check_movl, movl, set_parallel_gripper,
                     rel_joint_movj, rel_movl_user, get_angle, get_pose)
        if not all(callable(item) for item in functions):
            raise ValueError("controller_api_not_callable")
        self.check_movj, self.movj = check_movj, movj
        self.check_movl, self.movl = check_movl, movl
        self.set_parallel_gripper = set_parallel_gripper
        self.rel_joint_movj, self.rel_movl_user = rel_joint_movj, rel_movl_user
        self.get_angle, self.get_pose = get_angle, get_pose
        self.fault_access = fault_access or ControllerFaultAccess()

    @staticmethod
    def _check_result(value, vendor_api):
        code = value[0] if isinstance(value, tuple) and len(value) == 1 else value
        if type(code) is not int or not -2147483648 <= code <= 2147483647:
            raise ArmFault("preflight_result_unverified", "preflight", vendor_api, raw=value)
        if code != 0:
            raise ArmFault("path_check_rejected", "preflight", vendor_api, code, value)

    def check_linear(self, point, options):
        try:
            result = self.check_movl(point, options)
        except Exception as error:
            raise ArmFault("preflight_call_failed", "preflight", "CheckMovL", raw=str(error))
        self._check_result(result, "CheckMovL")

    def move_joint(self, joints, accel, speed):
        point, options = {"joint": list(joints)}, {"a": accel, "v": speed, "cp": 0}
        try:
            result = self.check_movj(point, options)
        except Exception as error:
            raise ArmFault("preflight_call_failed", "preflight", "CheckMovJ", raw=str(error))
        self._check_result(result, "CheckMovJ")
        self._invoke("MovJ", self.movj, point, options)

    @staticmethod
    def _invoke(name, function, *args):
        try:
            return function(*args)
        except Exception as error:
            raise ArmFault(str(error), "controller", name, getattr(error, "code", None), str(error))

    def move_linear(self, pose, user, tool, accel, speed):
        point = {"pose": list(pose)}
        options = {"user": user, "tool": tool, "a": accel, "v": speed, "r": 0}
        self.check_linear(point, options)
        self._invoke("MovL", self.movl, point, options)

    def gripper(self, width):
        self._invoke("SetParallelGripper", self.set_parallel_gripper, width)

    def jog_joint(self, joint_delta_deg, accel, speed):
        options = {"a": accel, "v": speed, "cp": 0}
        self._invoke("RelJointMovJ", self.rel_joint_movj, list(joint_delta_deg), options)

    def jog_xyz(self, translation_mm, user, tool, accel, speed):
        options = {"user": user, "tool": tool, "a": accel, "v": speed, "r": 0}
        raw_pose = None
        try:
            raw_pose = self.get_pose(user, tool)
            current = _feedback_vector(raw_pose, "pose",
                                       ("x", "y", "z", "rx", "ry", "rz"), "invalid_pose_feedback")
            target = [_number(current[i] + translation_mm[i], "invalid_pose_target") for i in range(3)] + list(current[3:])
        except Exception as error:
            raise ArmFault("xyz_preflight_pose_unavailable", "preflight", "GetPose", raw={"error": str(error), "result": raw_pose})
        self.check_linear({"pose": target}, options)
        self._invoke("RelMovLUser", self.rel_movl_user, list(translation_mm) + [0, 0, 0], options)

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
        self.fault_access = getattr(api, "fault_access", None) or ControllerFaultAccess()
        self.fault_history, self.next_fault_id = [], 1
        self._emit = None
        self._emitted = 0

    def _response(self, request, kind, payload=""):
        return encode_frame(MARKER, kind, request["sequence"], 0, payload)

    def _error(self, request, code):
        error = code if isinstance(code, Exception) else ArmFault(code)
        record = fault_record(error, self.clock_ms, self.next_fault_id)
        self.next_fault_id += 1
        self.fault_history.append(record)
        self.fault_history[:] = self.fault_history[-16:]
        self.error_code = record["error_code"]
        return (self._response(request, "ERROR", fault_payload(record)),)

    def _capabilities(self):
        access = self.fault_access
        return encode_fields((("fault_version", 1), ("xyz_preflight", int(isinstance(self.api, DobotControllerApi))),
                              ("controller_query", int(access.read is not None)),
                              ("controller_clear", int(access.read is not None and access.clear is not None)),
                              ("service_recover", int(access.read is not None))))

    def _fault_query(self, request):
        values = decode_fields(request["payload"], ("scope",))
        if values["scope"] == "controller":
            payload = controller_state_payload(self.fault_access.snapshot(self.clock_ms))
        elif values["scope"] == "service":
            record = self.fault_history[-1] if self.fault_history else fault_record(ArmFault("none"), self.clock_ms, 0)
            payload = fault_payload(record)
        else:
            raise ValueError("invalid_fault_scope")
        return (self._response(request, "FAULTSTATE", payload),)

    def _recover(self):
        if self.active_sequence is not None:
            raise ArmFault("request_in_flight", "recovery")
        self.fault_access.verify_recovery(self.clock_ms)
        # History and sequence deduplication remain intact. No motion is replayed.
        self.service_state, self.error_code = "ready", None

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
        if self._emit is not None:
            for reply in replies:
                self._emit(reply)
                self._emitted += 1
        try:
            function()
        except ValueError as error:
            self.service_state = "fault" if isinstance(error, ArmFault) and error.category == "controller" else "ready"
            self.active_sequence = None
            return replies + self._error(request, error)
        except RuntimeError as error:
            self.service_state, self.active_sequence = "fault", None
            return replies + self._error(request, error)
        except Exception as error:
            self.service_state, self.active_sequence = "fault", None
            return replies + self._error(request, ArmFault("execution_failed", "controller", raw=str(error)))
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
            if kind == "CAPS":
                decode_fields(request["payload"], ())
                return (self._response(request, "CAPSTATE", self._capabilities()),)
            if kind == "FAULTS":
                return self._fault_query(request)
            if kind in ("CLEARERR", "RECOVER"):
                values = decode_fields(request["payload"], ("confirm",))
                if values["confirm"] != "1":
                    raise ArmFault("recovery_confirmation_required", "recovery")
                if kind == "CLEARERR":
                    state = self.fault_access.clear_alarms(self.clock_ms)
                    payload = controller_state_payload(state)
                else:
                    self._recover()
                    payload = "recovery=service_ready;motion_resumed=0"
                return (self._response(request, "ACK"), self._response(request, "DONE", payload))
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
                values = decode_fields(request["payload"], ("translation_mm", "user", "tool", "accel_pct", "speed_pct", "blend_mm"))
                translation = _vector(values["translation_mm"], 3, "invalid_translation")
                user = _integer(values["user"], 0, 9, "invalid_user")
                tool = _integer(values["tool"], 0, 9, "invalid_tool")
                accel = _integer(values["accel_pct"], 1, 100, "invalid_acceleration")
                speed = _integer(values["speed_pct"], 1, 100, "invalid_speed")
                if values["blend_mm"] != "0": raise ValueError("blending_disabled")
                self.policy.relative(accel, speed)
                return self._run(request, lambda: self.api.jog_xyz(translation, user, tool, accel, speed), "primitive=jog_xyz;terminal_position=unknown")
            if kind == "GRIPPER":
                values = decode_fields(request["payload"], ("width_mm",))
                width = _integer(values["width_mm"], 0, 70, "invalid_gripper")
                self.policy.gripper(width)
                return self._run(request, lambda: self.api.gripper(width), "width_mm=%d;terminal_position=unknown" % width)
            return self._error(request, "unsupported_command")
        except (MotionLinkError, ValueError) as error:
            return self._error(request, error)

    def handle_message(self, request, received_at_ms=None, now_ms=None, emit=None):
        now, received = self.clock_ms() if now_ms is None else now_ms, self.clock_ms() if received_at_ms is None else received_at_ms
        fingerprint = encode_frame(MARKER, request["type"], request["sequence"], request["ttl_ms"], request["payload"])
        if request["sequence"] == self.last_sequence:
            replies = self.last_responses if fingerprint == self.last_fingerprint else self._error(request, "sequence_conflict")
        elif request["sequence"] < self.last_sequence:
            replies = self._error(request, "sequence_replay")
        else:
            self._emit, self._emitted = emit, 0
            try:
                replies = self._execute(request, received, now)
            finally:
                self._emit = None
            self.last_sequence, self.last_fingerprint, self.last_responses = request["sequence"], fingerprint, replies
            if emit is not None:
                for reply in replies[self._emitted:]:
                    emit(reply)
            return replies
        if emit is not None:
            for reply in replies:
                emit(reply)
        return replies

    def feed(self, data, received_at_ms=None, now_ms=None, emit=None):
        frames, errors = self.decoder.feed(data)
        received_at_ms = self.clock_ms() if received_at_ms is None else received_at_ms
        replies = []
        for frame in frames:
            replies.extend(self.handle_message(frame, received_at_ms, now_ms, emit))
        return tuple(replies), errors
