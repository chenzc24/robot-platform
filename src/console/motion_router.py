"""Route chassis commands directly to ESP32 and arm commands through MaixCam."""


MESSAGE_FIELDS = {"message_id", "target", "name", "ttl_ms", "payload"}
COMMAND_PAYLOAD_KEYS = {
    "chassis.ping": (),
    "chassis.status": (),
    "chassis.enable": (),
    "chassis.velocity": ("vx_mm_s", "vy_mm_s", "omega_mrad_s", "hold_ms"),
    "chassis.line_follow_start": ("direction",),
    "chassis.line_follow_status": (),
    "chassis.line_follow_stop": (),
    "chassis.stop": (),
    "chassis.disable": (),
    "arm.ping": (),
    "arm.status": (),
    "arm.move_joint": ("joint_deg", "accel_pct", "speed_pct"),
    "arm.move_linear": ("pose", "user", "tool", "accel_pct", "speed_pct"),
    "arm.gripper": ("width_mm",),
}
ADMISSION_REQUIRED = {
    "chassis.enable",
    "chassis.velocity",
    "chassis.line_follow_start",
    "arm.move_joint",
    "arm.move_linear",
    "arm.gripper",
}


class MotionRouterError(RuntimeError):
    def __init__(self, code):
        RuntimeError.__init__(self, code)
        self.code = code


def _validate_message(message):
    if not isinstance(message, dict) or set(message) != MESSAGE_FIELDS:
        raise MotionRouterError("invalid_message_fields")
    if not isinstance(message["message_id"], str) or not message["message_id"]:
        raise MotionRouterError("invalid_message_id")
    if message["target"] not in ("chassis", "arm"):
        raise MotionRouterError("invalid_target")
    if isinstance(message["ttl_ms"], bool) or not isinstance(message["ttl_ms"], int):
        raise MotionRouterError("invalid_ttl")
    if not 100 <= message["ttl_ms"] <= 60000:
        raise MotionRouterError("invalid_ttl")
    expected = COMMAND_PAYLOAD_KEYS.get(message["name"])
    if expected is None:
        raise MotionRouterError("unsupported_command")
    if message["name"].split(".", 1)[0] != message["target"]:
        raise MotionRouterError("target_mismatch")
    if not isinstance(message["payload"], dict) or set(message["payload"]) != set(expected):
        raise MotionRouterError("invalid_payload_fields")
    return message


class DualSessionMotionRouter:
    """Keep transport ownership flat while applying one cross-device admission gate."""

    def __init__(self, chassis_session, maixcam_arm_session, admission=None):
        self.chassis = chassis_session
        self.arm = maixcam_arm_session
        self.admission = admission

    def _admit(self, message):
        if message["name"] not in ADMISSION_REQUIRED:
            return
        if self.admission is None:
            raise MotionRouterError("admission_unavailable")
        try:
            allowed = self.admission(
                message["target"], message["name"], message["payload"]
            )
        except Exception as error:
            raise MotionRouterError("admission_failed") from error
        if allowed is not True:
            raise MotionRouterError("admission_rejected")

    def dispatch(self, message, remaining_ttl_ms=None):
        message = _validate_message(message)
        ttl_ms = message["ttl_ms"] if remaining_ttl_ms is None else remaining_ttl_ms
        if isinstance(ttl_ms, bool) or not isinstance(ttl_ms, int) or ttl_ms < 100:
            raise MotionRouterError("insufficient_remaining_ttl")
        ttl_ms = min(ttl_ms, message["ttl_ms"])
        self._admit(message)
        payload = message["payload"]
        name = message["name"]

        try:
            if name == "chassis.ping":
                result = self.chassis.ping(min(ttl_ms, 5000))
            elif name == "chassis.status":
                result = self.chassis.status(min(ttl_ms, 5000))
            elif name == "chassis.enable":
                result = self.chassis.enable(min(ttl_ms, 5000))
            elif name == "chassis.velocity":
                result = self.chassis.velocity(
                    payload["vx_mm_s"],
                    payload["vy_mm_s"],
                    payload["omega_mrad_s"],
                    payload["hold_ms"],
                    min(ttl_ms, 5000),
                )
            elif name == "chassis.line_follow_start":
                result = self.chassis.line_follow_start(
                    payload["direction"], min(ttl_ms, 5000)
                )
            elif name == "chassis.line_follow_status":
                result = self.chassis.line_follow_status(min(ttl_ms, 5000))
            elif name == "chassis.line_follow_stop":
                result = self.chassis.line_follow_stop(min(ttl_ms, 5000))
            elif name == "chassis.stop":
                result = self.chassis.stop(min(ttl_ms, 5000))
            elif name == "chassis.disable":
                result = self.chassis.disable(min(ttl_ms, 5000))
            elif name == "arm.ping":
                result = self.arm.ping(ttl_ms)
            elif name == "arm.status":
                result = self.arm.status(ttl_ms)
            elif name == "arm.move_joint":
                result = self.arm.move_joint(
                    payload["joint_deg"],
                    payload["accel_pct"],
                    payload["speed_pct"],
                    ttl_ms,
                )
            elif name == "arm.move_linear":
                result = self.arm.move_linear(
                    payload["pose"],
                    payload["user"],
                    payload["tool"],
                    payload["accel_pct"],
                    payload["speed_pct"],
                    ttl_ms,
                )
            elif name == "arm.gripper":
                result = self.arm.gripper(payload["width_mm"], ttl_ms)
            else:
                raise MotionRouterError("unsupported_command")
        except MotionRouterError:
            raise
        except Exception as error:
            code = getattr(error, "code", None) or "downstream_failed"
            raise MotionRouterError(code) from error

        return {
            "correlation_id": message["message_id"],
            "target": message["target"],
            "automatic_retry": False,
            "result": result,
        }
