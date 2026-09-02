"""Flat robot connection and managed-process command line interface."""

import argparse
from dataclasses import asdict, dataclass
import json
import os
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEV_TOOLS = ROOT / "tools" / "dev"
if str(DEV_TOOLS) not in sys.path:
    sys.path.insert(0, str(DEV_TOOLS))

from connection_manager import (  # noqa: E402
    ConnectionLock,
    ConnectionManager,
    OperationRefused,
)


EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_REFUSED = 3


@dataclass
class Feedback:
    """Stable operation result for text and JSON output."""

    level: str
    operation: str
    code: str
    detail: str
    action: str = ""
    output: str = ""

    def as_dict(self):
        return asdict(self)


def _add_connection_options(parser):
    parser.add_argument(
        "--esp32-host",
        default=os.environ.get("ROBOT_ESP32_HOST"),
        help="Current ESP32 IPv4 address; discovery is used when omitted",
    )
    _add_common_options(parser)


def _add_common_options(parser):
    parser.add_argument(
        "--maixcam-host",
        default="maixcam-6c7d.local",
        help="MaixCam mDNS name used by RTSP and the local relay",
    )
    parser.add_argument(
        "--ssh-target",
        default="robot-maixcam",
        help="OpenSSH host alias for MaixCam maintenance",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")


def _add_arm_options(parser):
    parser.add_argument(
        "--arm-host",
        default=os.environ.get("ROBOT_ARM_HOST", "maixcam-6c7d.local"),
        help="MaixCam arm-command endpoint host",
    )
    parser.add_argument(
        "--arm-port",
        default=int(os.environ.get("ROBOT_ARM_PORT", "8780")),
        type=int,
        help="MaixCam arm-command endpoint TCP port",
    )
    parser.add_argument(
        "--timeout",
        default=3.0,
        type=float,
        help="Connection timeout in seconds",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command, help_text in (
        ("connect", "Ensure required links and the local video relay"),
        ("status", "Read the flat connection status"),
        ("details", "Read and expand every connection check"),
    ):
        subparser = subparsers.add_parser(command, help=help_text)
        _add_connection_options(subparser)

    disconnect = subparsers.add_parser(
        "disconnect",
        help="Stop only the managed local video relay",
    )
    _add_common_options(disconnect)

    processes = subparsers.add_parser("ps", help="Show managed project processes")
    processes.add_argument("target", choices=("relay", "maixcam"))
    _add_common_options(processes)

    logs = subparsers.add_parser("logs", help="Show recent managed service logs")
    logs.add_argument("target", choices=("relay", "maixcam-video"))
    logs.add_argument("--lines", type=int, default=80)
    _add_common_options(logs)

    stop = subparsers.add_parser("stop", help="Stop one named managed service")
    stop.add_argument("target", choices=("relay", "maixcam-video"))
    _add_common_options(stop)

    restart = subparsers.add_parser("restart", help="Restart one named managed service")
    restart.add_argument("target", choices=("relay", "maixcam-video"))
    _add_common_options(restart)

    kill = subparsers.add_parser(
        "kill",
        help="Force-terminate one named and ownership-verified service",
    )
    kill.add_argument("target", choices=("relay", "maixcam-video"))
    kill.add_argument("--force", action="store_true", help="Required safety acknowledgement")
    kill.add_argument("--yes", action="store_true", help="Skip the interactive confirmation")
    _add_common_options(kill)

    reboot = subparsers.add_parser("reboot", help="Reboot one explicitly named device")
    reboot.add_argument("device", choices=("maixcam", "esp32"))
    reboot.add_argument("--yes", action="store_true", help="Skip the interactive confirmation")
    _add_common_options(reboot)

    arm = subparsers.add_parser(
        "arm",
        help="Inspect or control the MaixCam robot-arm endpoint",
    )
    arm_commands = arm.add_subparsers(dest="arm_command", required=True)
    for command, help_text in (
        ("ping", "Send one arm PING and print its terminal lifecycle"),
        ("status", "Send one arm STATUS and print its terminal lifecycle"),
        ("check", "Run one PING then one STATUS on the same arm session"),
    ):
        subparser = arm_commands.add_parser(command, help=help_text)
        _add_arm_options(subparser)
    jog_joint = arm_commands.add_parser("jog-joint", help="Move one joint by a signed relative angle")
    jog_joint.add_argument("--joint", required=True, type=int, choices=range(1, 7))
    jog_joint.add_argument("--delta", type=float, default=2.0, help="signed degrees")
    jog_joint.add_argument("--speed", type=int, default=5, choices=range(1, 101))
    jog_joint.add_argument("--accel", type=int, default=5, choices=range(1, 101))
    _add_arm_options(jog_joint)
    jog_xyz = arm_commands.add_parser("jog-xyz", help="Move one user-coordinate axis by a signed distance")
    jog_xyz.add_argument("--axis", required=True, choices=("x", "y", "z"))
    jog_xyz.add_argument("--delta", type=float, default=5.0, help="signed millimetres")
    jog_xyz.add_argument("--user", type=int, default=0, choices=range(0, 10))
    jog_xyz.add_argument("--tool", type=int, default=0, choices=range(0, 10))
    jog_xyz.add_argument("--speed", type=int, default=5, choices=range(1, 101))
    jog_xyz.add_argument("--accel", type=int, default=5, choices=range(1, 101))
    _add_arm_options(jog_xyz)
    return parser


def _manager(args, manager_factory):
    return manager_factory(
        maixcam_host=args.maixcam_host,
        ssh_target=args.ssh_target,
    )


def _emit_report(report, as_json=False, details=False):
    if as_json:
        print(json.dumps(report.as_dict(), sort_keys=True))
    else:
        states = "  ".join(
            "%s=%s" % (check.name, "online" if check.ok else "error")
            for check in report.checks
        )
        suffix = "  changed=true" if report.changed else ""
        print("%s  %s%s" % (report.level, states, suffix))
        for check in report.checks:
            if details or not check.ok:
                marker = "OK" if check.ok else "ERROR"
                print("%s %s %s: %s" % (marker, check.name, check.code, check.detail))
                if check.action:
                    print("ACTION %s" % check.action)
    return EXIT_OK if report.level == "READY" else EXIT_FAILED


def _emit_feedback(feedback, as_json=False, exit_code=None):
    if as_json:
        print(json.dumps(feedback.as_dict(), sort_keys=True))
    else:
        print(
            "%s %s %s: %s"
            % (feedback.level, feedback.operation, feedback.code, feedback.detail)
        )
        if feedback.output:
            print(feedback.output)
        if feedback.action:
            print("ACTION %s" % feedback.action)
    if exit_code is not None:
        return exit_code
    return EXIT_OK if feedback.level == "READY" else EXIT_FAILED


def _from_command(operation, result, success_detail):
    if result.returncode == 0:
        return Feedback(
            "READY",
            operation,
            "ok",
            success_detail,
            output=result.stdout,
        )
    if result.returncode == EXIT_REFUSED:
        return Feedback(
            "DEGRADED",
            operation,
            "operation_refused",
            "The target failed ownership or safety validation",
            action="Run: .\\robot details",
            output=result.stderr,
        )
    return Feedback(
        "DEGRADED",
        operation,
        "operation_failed",
        "The managed operation failed",
        action="Inspect the named service logs",
        output=result.stderr or result.stdout,
    )


def _confirmed(prompt, assume_yes, input_func):
    if assume_yes:
        return True
    answer = input_func("%s [y/N] " % prompt).strip().lower()
    return answer in ("y", "yes")


def _ensure_arm_client_import_paths():
    """Expose the local shared protocol and console client to this flat tool."""
    for directory in (ROOT / "protocol", ROOT / "src" / "console"):
        path = str(directory)
        if path not in sys.path:
            sys.path.insert(0, path)


def _default_arm_client_factory(host, port, timeout_seconds, session_id):
    _ensure_arm_client_import_paths()
    from maixcam_arm_client import MaixCamArmClient, open_connection

    connection = open_connection(host, port, timeout_seconds)
    return MaixCamArmClient(connection, session_id)


def _close_arm_client(client):
    close = getattr(getattr(client, "connection", None), "close", None)
    if callable(close):
        close()


def _terminal_lifecycle(result):
    if not isinstance(result, list) or not result:
        return None, {}
    terminal = result[-1]
    if not isinstance(terminal, dict):
        return None, {}
    return terminal.get("lifecycle"), terminal.get("payload") or {}


def _diagnostic_output(command, result):
    lifecycle, payload = _terminal_lifecycle(result)
    return json.dumps(
        {"command": command, "lifecycle": lifecycle, "payload": payload},
        sort_keys=True,
    )


def _run_arm_diagnostic(args, arm_client_factory):
    """Run one non-retrying arm operation and always close its socket."""
    client = None
    operation = "arm.%s" % args.arm_command
    try:
        client = arm_client_factory(
            args.arm_host,
            args.arm_port,
            args.timeout,
            "robot-cli",
        )
        if args.arm_command == "ping":
            result = client.ping()
            lifecycle, _payload = _terminal_lifecycle(result)
            if lifecycle != "DONE":
                return Feedback("DEGRADED", operation, "unexpected_lifecycle", "PING did not complete", output=_diagnostic_output("arm.ping", result))
            return Feedback("READY", operation, "ok", "arm PING completed", output=_diagnostic_output("arm.ping", result))

        if args.arm_command == "status":
            result = client.status()
            lifecycle, _payload = _terminal_lifecycle(result)
            if lifecycle != "DONE":
                return Feedback("DEGRADED", operation, "unexpected_lifecycle", "STATUS did not complete", output=_diagnostic_output("arm.status", result))
            return Feedback("READY", operation, "ok", "arm STATUS completed", output=_diagnostic_output("arm.status", result))

        if args.arm_command == "check":
            ping, status = client.ping(), client.status()
            ping_lifecycle, _ping_payload = _terminal_lifecycle(ping)
            status_lifecycle, status_payload = _terminal_lifecycle(status)
            output = json.dumps(
                {
                    "ping": json.loads(_diagnostic_output("arm.ping", ping)),
                    "status": json.loads(_diagnostic_output("arm.status", status)),
                },
                sort_keys=True,
            )
            if ping_lifecycle != "DONE" or status_lifecycle != "DONE":
                return Feedback("DEGRADED", operation, "unexpected_lifecycle", "PING or STATUS did not complete", output=output)
            state = status_payload.get("downstream_payload", "unknown")
            return Feedback("READY", operation, "ok", "arm PING and STATUS completed", output=output, action="Controller state: %s" % state)

        if args.arm_command == "jog-joint":
            delta = [0.0] * 6
            delta[args.joint - 1] = args.delta
            result = client.jog_joint(delta, accel_pct=args.accel, speed_pct=args.speed)
            lifecycle, payload = _terminal_lifecycle(result)
            output = _diagnostic_output("arm.jog_joint", result)
            if lifecycle == "DONE":
                return Feedback("READY", operation, "ok", "joint jog completed", output=output)
            return Feedback("DEGRADED", operation, payload.get("error_code", "unexpected_lifecycle"), "joint jog did not complete", output=output)

        if args.arm_command == "jog-xyz":
            delta = [0.0] * 3
            delta[("x", "y", "z").index(args.axis)] = args.delta
            result = client.jog_xyz(delta, user=args.user, tool=args.tool, accel_pct=args.accel, speed_pct=args.speed)
            lifecycle, payload = _terminal_lifecycle(result)
            output = _diagnostic_output("arm.jog_xyz", result)
            if lifecycle == "DONE":
                return Feedback("READY", operation, "ok", "XYZ jog completed", output=output)
            return Feedback("DEGRADED", operation, payload.get("error_code", "unexpected_lifecycle"), "XYZ jog did not complete", output=output)

        raise ValueError("unsupported_arm_diagnostic")
    except Exception as error:
        code = getattr(error, "code", None) or type(error).__name__.lower()
        return Feedback("DEGRADED", operation, code, "arm diagnostic request failed", action="Run: .\\robot arm check --json")
    finally:
        if client is not None:
            try:
                _close_arm_client(client)
            except Exception:
                pass


def _run_maintenance(args, manager, input_func):
    if args.command == "disconnect":
        result = manager.relay_action("stop")
        feedback = _from_command("disconnect", result, "local relay stopped")
        return feedback, None

    if args.command == "ps":
        result = (
            manager.relay_action("status")
            if args.target == "relay"
            else manager.remote_project_processes()
        )
        feedback = _from_command("ps.%s" % args.target, result, "process state read")
        return feedback, None

    if args.command == "logs":
        result = (
            manager.relay_logs(args.lines)
            if args.target == "relay"
            else manager.remote_video_logs(args.lines)
        )
        feedback = _from_command("logs.%s" % args.target, result, "recent logs read")
        return feedback, None

    if args.command == "stop":
        result = (
            manager.relay_action("stop")
            if args.target == "relay"
            else manager.remote_video_stop(force=False)
        )
        feedback = _from_command("stop.%s" % args.target, result, "service stopped")
        return feedback, None

    if args.command == "restart":
        if args.target == "relay":
            stop_result = manager.relay_action("stop")
            if stop_result.returncode != 0:
                return _from_command("restart.relay", stop_result, ""), None
            result = manager.relay_action("start")
        else:
            stop_result = manager.remote_video_stop(force=False)
            if stop_result.returncode != 0:
                return _from_command("restart.maixcam-video", stop_result, ""), None
            result = manager.remote_video_start()
        feedback = _from_command(
            "restart.%s" % args.target,
            result,
            "service restarted",
        )
        if args.target == "maixcam-video" and feedback.level != "READY":
            feedback.code = "camera_reinit_failed"
            feedback.action = "Run: .\\robot reboot maixcam"
        return feedback, None

    if args.command == "kill":
        if not args.force:
            return Feedback(
                "DEGRADED",
                "kill.%s" % args.target,
                "force_required",
                "Force termination requires --force",
            ), EXIT_REFUSED
        if not _confirmed("Force-terminate %s?" % args.target, args.yes, input_func):
            return Feedback(
                "DEGRADED",
                "kill.%s" % args.target,
                "confirmation_required",
                "Force termination was not confirmed",
            ), EXIT_REFUSED
        result = (
            manager.relay_action("stop")
            if args.target == "relay"
            else manager.remote_video_stop(force=True)
        )
        feedback = _from_command("kill.%s" % args.target, result, "service terminated")
        return feedback, None

    if args.command == "reboot":
        if args.device == "esp32":
            return Feedback(
                "DEGRADED",
                "reboot.esp32",
                "esp32_reboot_locked",
                "ESP32 reboot is locked while the legacy motion application is deployed",
                action="Deploy and validate the safe runtime before unlocking reboot",
            ), EXIT_REFUSED
        if not _confirmed("Reboot MaixCam?" , args.yes, input_func):
            return Feedback(
                "DEGRADED",
                "reboot.maixcam",
                "confirmation_required",
                "Device reboot was not confirmed",
            ), EXIT_REFUSED
        result = manager.reboot_maixcam()
        feedback = _from_command("reboot.maixcam", result, "reboot requested")
        if feedback.level == "READY":
            feedback.action = "Wait for SSH, then exit num before starting video"
        return feedback, None

    raise ValueError("unsupported maintenance command")


def main(
    argv=None,
    manager_factory=ConnectionManager,
    lock_factory=ConnectionLock,
    input_func=input,
    arm_client_factory=_default_arm_client_factory,
):
    args = build_parser().parse_args(argv)
    try:
        with lock_factory():
            if args.command == "arm":
                return _emit_feedback(
                    _run_arm_diagnostic(args, arm_client_factory),
                    as_json=args.json,
                )
            manager = _manager(args, manager_factory)
            if args.command in ("connect", "status", "details"):
                report = manager.report(
                    explicit_esp32_host=args.esp32_host,
                    ensure_relay=args.command == "connect",
                )
                return _emit_report(
                    report,
                    as_json=args.json,
                    details=args.command == "details",
                )
            feedback, exit_override = _run_maintenance(args, manager, input_func)
            return _emit_feedback(
                feedback,
                as_json=args.json,
                exit_code=exit_override,
            )
    except OperationRefused as error:
        feedback = Feedback(
            "DEGRADED",
            args.command,
            "operation_locked",
            str(error),
            action="Wait for the active robot CLI command to finish",
        )
        return _emit_feedback(feedback, as_json=args.json, exit_code=EXIT_REFUSED)


if __name__ == "__main__":
    raise SystemExit(main())
