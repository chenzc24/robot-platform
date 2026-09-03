"""Pure-Python device session primitives shared by desktop and web consoles."""

import os
import sys
from dataclasses import dataclass
from pathlib import Path


SAFE_CHASSIS_COMMANDS = {"ping", "status"}
SAFE_ARM_COMMANDS = {"ping", "status", "capabilities", "faults"}
RECOVERY_ARM_COMMANDS = {"clear_errors", "recover_service"}
MOTION_CHASSIS_COMMANDS = {"enable", "velocity", "stop", "disable"}
MOTION_ARM_COMMANDS = {
    "move_joint",
    "move_linear",
    "jog_joint",
    "jog_xyz",
    "gripper",
}


@dataclass(frozen=True)
class SessionResult:
    target: str
    command: str
    lifecycle: object
    code: str
    payload: object = None


@dataclass(frozen=True)
class SessionFault:
    target: str
    code: str
    detail: str
    state_changing: bool


class ArmLifecycleError(RuntimeError):
    """Preserve a non-success arm outcome instead of returning it as success."""

    def __init__(self, code, lifecycle, explicit_terminal=False, payload=None):
        super().__init__(code)
        self.code = code
        self.lifecycle = lifecycle
        self.explicit_terminal = explicit_terminal
        self.payload = payload or {}


class ArmLifecycleRejection(ArmLifecycleError):
    """A MaixCam endpoint explicitly rejected a request without link failure."""

    explicit_rejection = True

    def __init__(self, code):
        super().__init__(code, "REJECTED", explicit_terminal=True)


def source_root():
    return Path(__file__).resolve().parents[2]


def ensure_runtime_import_paths():
    """Expose local protocol and console clients without importing a UI."""
    for directory in (source_root() / "protocol", source_root() / "src" / "console"):
        path = str(directory)
        if path not in sys.path:
            sys.path.insert(0, path)


def default_chassis_factory(config):
    """Create and authenticate one chassis client after explicit connect."""
    if not config.complete:
        raise ValueError("chassis_configuration_incomplete")
    credential = os.environ.get(config.credential_env)
    if not credential:
        raise ValueError("chassis_credential_unavailable")
    ensure_runtime_import_paths()
    from chassis_motion_tcp_client import ChassisMotionTcpClient, open_connection

    connection = open_connection(config.host, config.port, config.connect_timeout_seconds)
    client = ChassisMotionTcpClient(connection)
    try:
        client.hello(config.client_id, credential)
    except Exception:
        connection.close()
        raise
    return client


def default_arm_factory(config):
    """Create one MaixCam arm client after explicit connect."""
    if not config.complete:
        raise ValueError("arm_configuration_incomplete")
    ensure_runtime_import_paths()
    from maixcam_arm_client import MaixCamArmClient, open_connection

    connection = open_connection(config.host, config.port, config.connect_timeout_seconds)
    return MaixCamArmClient(connection, config.session_id)


def close_client(client):
    connection = getattr(client, "connection", None)
    close = getattr(connection, "close", None)
    if callable(close):
        close()


def dispatch_chassis(client, command, payload=None):
    payload = payload or {}
    handlers = {
        "ping": client.ping,
        "status": client.status,
        "enable": client.enable,
        "velocity": lambda: client.velocity(
            payload["vx_mm_s"],
            payload["vy_mm_s"],
            payload["omega_mrad_s"],
            payload.get("hold_ms", 250),
        ),
        "stop": client.stop,
        "disable": client.disable,
    }
    if command not in handlers:
        raise ValueError("unsupported_chassis_command")
    return handlers[command]()


def dispatch_arm(client, command, payload=None):
    payload = payload or {}
    handlers = {
        "ping": client.ping,
        "status": client.status,
        "capabilities": lambda: client.capabilities(),
        "faults": lambda: client.faults(payload.get("scope", "service")),
        "clear_errors": lambda: client.clear_errors(confirm=payload.get("confirm", False)),
        "recover_service": lambda: client.recover_service(confirm=payload.get("confirm", False)),
        "move_joint": lambda: client.move_joint(
            payload["joint_deg"],
            payload.get("accel_pct", 5),
            payload.get("speed_pct", 5),
        ),
        "move_linear": lambda: client.move_linear(
            payload["pose"],
            payload.get("user", 0),
            payload.get("tool", 0),
            payload.get("accel_pct", 5),
            payload.get("speed_pct", 5),
        ),
        "jog_joint": lambda: client.jog_joint(
            payload["joint_delta_deg"],
            payload.get("accel_pct", 5),
            payload.get("speed_pct", 5),
        ),
        "jog_xyz": lambda: client.jog_xyz(
            payload["translation_mm"],
            payload.get("user", 0),
            payload.get("tool", 0),
            payload.get("accel_pct", 5),
            payload.get("speed_pct", 5),
        ),
        "gripper": lambda: client.gripper(payload["width_mm"]),
    }
    if command not in handlers:
        raise ValueError("unsupported_arm_command")
    responses = handlers[command]()
    terminal = responses[-1] if isinstance(responses, (list, tuple)) and responses else None
    if not isinstance(terminal, dict) or not isinstance(terminal.get("payload"), dict):
        raise ArmLifecycleError("arm_invalid_terminal_response", "UNKNOWN" if command in MOTION_ARM_COMMANDS | RECOVERY_ARM_COMMANDS else "FAULT")
    outcome, reply = terminal.get("lifecycle"), terminal["payload"]
    if outcome == "REJECTED":
        raise ArmLifecycleRejection(reply.get("error_code", "arm_request_rejected"))
    if outcome in {"FAULT", "UNKNOWN"}:
        raise ArmLifecycleError(reply.get("error_code", "arm_" + outcome.lower()), outcome, explicit_terminal=True, payload=reply)
    if outcome != "DONE":
        raise ArmLifecycleError("arm_invalid_terminal_response", "UNKNOWN" if command in MOTION_ARM_COMMANDS | RECOVERY_ARM_COMMANDS else "FAULT")
    return responses
