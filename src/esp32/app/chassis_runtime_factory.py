"""Safe ESP32 composition. The L2 path intentionally does not open CAN."""

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
