"""Command-routing and feedback tests for the flat robot CLI."""

from contextlib import redirect_stdout
import io
import json
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
DEV_TOOLS = TOOLS / "dev"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(DEV_TOOLS))

from connection_manager import CommandResult, ConnectionReport, LinkCheck
import robot_cli


class NoopLock:
    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        return None


class FakeManager:
    instances = []

    def __init__(self, **options):
        self.options = options
        self.calls = []
        type(self).instances.append(self)

    def report(self, explicit_esp32_host=None, ensure_relay=False):
        self.calls.append(("report", explicit_esp32_host, ensure_relay))
        return ConnectionReport(
            "READY",
            [
                LinkCheck("maixcam", True, "ok", "SSH ready"),
                LinkCheck("esp32", True, "ok", "WebREPL port ready"),
                LinkCheck("camera", True, "ok", "device RTSP ready"),
                LinkCheck("video", True, "ok", "local relay ready"),
            ],
        )

    def relay_action(self, action):
        self.calls.append(("relay_action", action))
        return CommandResult(0, "RELAY_%s" % action.upper())

    def relay_logs(self, lines):
        self.calls.append(("relay_logs", lines))
        return CommandResult(0, "relay log")

    def remote_project_processes(self):
        self.calls.append(("remote_project_processes",))
        return CommandResult(0, "123 python3 rtsp_server.py")

    def remote_video_logs(self, lines):
        self.calls.append(("remote_video_logs", lines))
        return CommandResult(0, "video log")

    def remote_video_stop(self, force=False):
        self.calls.append(("remote_video_stop", force))
        return CommandResult(0, "RTSP_STOPPED")

    def remote_video_start(self):
        self.calls.append(("remote_video_start",))
        return CommandResult(0, "RTSP_STARTED")

    def reboot_maixcam(self):
        self.calls.append(("reboot_maixcam",))
        return CommandResult(0, "REBOOT_REQUESTED")


def run_cli(arguments, input_value="n"):
    FakeManager.instances = []
    output = io.StringIO()
    with redirect_stdout(output):
        exit_code = robot_cli.main(
            arguments,
            manager_factory=FakeManager,
            lock_factory=NoopLock,
            input_func=lambda _prompt: input_value,
        )
    return exit_code, output.getvalue(), FakeManager.instances[-1]


class RobotCliTests(unittest.TestCase):
    def test_status_json_is_flat_and_machine_readable(self):
        exit_code, output, manager = run_cli(
            ["status", "--json", "--esp32-host", "192.0.2.30"]
        )
        payload = json.loads(output)
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["level"], "READY")
        self.assertEqual(len(payload["checks"]), 4)
        self.assertEqual(manager.calls, [("report", "192.0.2.30", False)])

    def test_connect_is_the_only_report_command_that_ensures_relay(self):
        exit_code, _output, manager = run_cli(["connect"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(manager.calls, [("report", None, True)])

    def test_restart_relay_stops_before_starting(self):
        exit_code, _output, manager = run_cli(["restart", "relay"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            manager.calls,
            [("relay_action", "stop"), ("relay_action", "start")],
        )

    def test_restart_maixcam_video_uses_normal_stop(self):
        exit_code, _output, manager = run_cli(["restart", "maixcam-video"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            manager.calls,
            [("remote_video_stop", False), ("remote_video_start",)],
        )

    def test_force_kill_requires_both_flags_or_confirmation(self):
        exit_code, output, _manager = run_cli(["kill", "maixcam-video"])
        self.assertEqual(exit_code, 3)
        self.assertIn("force_required", output)

        exit_code, output, _manager = run_cli(
            ["kill", "maixcam-video", "--force"]
        )
        self.assertEqual(exit_code, 3)
        self.assertIn("confirmation_required", output)

        exit_code, _output, manager = run_cli(
            ["kill", "maixcam-video", "--force", "--yes"]
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(manager.calls, [("remote_video_stop", True)])

    def test_esp32_reboot_is_locked_before_any_device_call(self):
        exit_code, output, manager = run_cli(["reboot", "esp32", "--yes"])
        self.assertEqual(exit_code, 3)
        self.assertIn("esp32_reboot_locked", output)
        self.assertEqual(manager.calls, [])

    def test_maixcam_reboot_requires_confirmation(self):
        exit_code, _output, manager = run_cli(["reboot", "maixcam"])
        self.assertEqual(exit_code, 3)
        self.assertEqual(manager.calls, [])

        exit_code, output, manager = run_cli(
            ["reboot", "maixcam", "--yes", "--json"]
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(output)["code"], "ok")
        self.assertEqual(manager.calls, [("reboot_maixcam",)])


if __name__ == "__main__":
    unittest.main()
