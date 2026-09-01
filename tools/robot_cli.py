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
):
    args = build_parser().parse_args(argv)
    try:
        with lock_factory():
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
