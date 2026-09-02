"""Fail-closed ESP32 L2 and L3 runtime composition."""

from chassis_motion_tcp_service import ChassisMotionTcpService, fixed_credential_verifier
from control_lease import ControlLease


class NoMotionChassis:
    """L2 dependency with no motor bus or CAN side effect."""
    state = "disabled"
    def enable_motors(self): raise RuntimeError("motion_disabled")
    def drive(self, _vx, _vy, _omega): raise RuntimeError("motion_disabled")
    def stop(self): self.state = "disabled"
    def disable(self): self.state = "disabled"


def runtime_credential():
    try:
        from secrets import RUNTIME_CREDENTIAL
    except ImportError:
        return None
    return RUNTIME_CREDENTIAL if isinstance(RUNTIME_CREDENTIAL, str) and RUNTIME_CREDENTIAL else None


def make_l2_service(transport):
    """Create the first deployable v2 service: network only, motion impossible."""
    credential = runtime_credential()
    verifier = fixed_credential_verifier(credential) if credential else None
    return ChassisMotionTcpService(transport, NoMotionChassis(), ControlLease(), authorize=verifier, motion_permitted=False)


def _local_config():
    try:
        import device_config
    except ImportError:
        raise RuntimeError("l3_device_config_missing")
    return device_config


def _positive_int(config, field, maximum):
    value = getattr(config, field, None)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise RuntimeError("invalid_%s" % field.lower())
    return value


def make_l3_service_factory():
    """Build one real CAN chassis and a per-connection L3 service factory.

    The startup path sends only a best-effort zero/disable sequence. Motion
    remains blocked unless the ignored local configuration explicitly sets
    `L3_MOTION_PERMITTED` to `True`.
    """
    from can_runtime import create_can
    from chassis_control import SafeMecanumChassis
    from motor_bus import MotorBus

    config = _local_config()
    chassis = SafeMecanumChassis(MotorBus(create_can(config)))
    startup_fault = None
    try:
        chassis.disable()
    except Exception:
        startup_fault = "startup_safe_output_failed"

    credential = runtime_credential()
    verifier = fixed_credential_verifier(credential) if credential else None
    motion_permitted = getattr(config, "L3_MOTION_PERMITTED", False) is True
    max_linear_mm_s = _positive_int(config, "L3_MAX_LINEAR_SPEED_MM_S", 100)
    max_omega_mrad_s = _positive_int(config, "L3_MAX_OMEGA_MRAD_S", 200)
    max_hold_ms = _positive_int(config, "L3_MAX_HOLD_MS", 250)

    def make_service(transport):
        service = ChassisMotionTcpService(
            transport,
            chassis,
            ControlLease(),
            authorize=verifier,
            motion_permitted=motion_permitted,
            max_linear_mm_s=max_linear_mm_s,
            max_omega_mrad_s=max_omega_mrad_s,
            max_hold_ms=max_hold_ms,
        )
        if startup_fault is not None:
            service.service_state = "fault"
            service.error_code = startup_fault
        return service

    return make_service
