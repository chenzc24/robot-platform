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

    def report(
        self,
        explicit_esp32_host=None,
        ensure_relay=False,
        include_esp32=True,
    ):
        self.calls.append(
            ("report", explicit_esp32_host, ensure_relay, include_esp32)
        )
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


def run_cli(arguments, input_value="n", arm_client_factory=None):
    FakeManager.instances = []
    output = io.StringIO()
    with redirect_stdout(output):
        kwargs = {
            "manager_factory": FakeManager,
            "lock_factory": NoopLock,
            "input_func": lambda _prompt: input_value,
        }
        if arm_client_factory is not None:
            kwargs["arm_client_factory"] = arm_client_factory
        exit_code = robot_cli.main(arguments, **kwargs)
    manager = FakeManager.instances[-1] if FakeManager.instances else None
    return exit_code, output.getvalue(), manager


class FakeArmConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeArmClient:
    def __init__(self, outcomes):
        self.connection = FakeArmConnection()
        self.outcomes = outcomes
        self.calls = []

    def ping(self):
        self.calls.append("ping")
        return self.outcomes["ping"]

    def status(self):
        self.calls.append("status")
        return self.outcomes["status"]

    def move_joint(self, joint_deg, accel_pct=5, speed_pct=5):
        self.calls.append(("move_joint", tuple(joint_deg), accel_pct, speed_pct))
        return self.outcomes["move_joint"]

    def jog_joint(self, joint_delta_deg, accel_pct=5, speed_pct=5):
        self.calls.append(("jog_joint", tuple(joint_delta_deg), accel_pct, speed_pct))
        return self.outcomes["jog_joint"]

    def jog_xyz(self, translation_mm, user=0, tool=0, accel_pct=5, speed_pct=5):
        self.calls.append(("jog_xyz", tuple(translation_mm), user, tool, accel_pct, speed_pct))
        return self.outcomes["jog_xyz"]


def lifecycle(state, payload=None):
    return [{"lifecycle": state, "payload": payload or {}}]


def arm_factory_with(outcomes, created):
    def factory(host, port, timeout, session_id):
        created.append((host, port, timeout, session_id))
        return FakeArmClient(outcomes)
    return factory


class RobotCliTests(unittest.TestCase):
    def test_status_json_is_flat_and_machine_readable(self):
        exit_code, output, manager = run_cli(
            ["status", "--json", "--esp32-host", "192.0.2.30"]
        )
        payload = json.loads(output)
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["level"], "READY")
        self.assertEqual(len(payload["checks"]), 4)
        self.assertEqual(manager.calls, [("report", "192.0.2.30", False, True)])

    def test_connect_is_the_only_report_command_that_ensures_relay(self):
        exit_code, _output, manager = run_cli(["connect"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(manager.calls, [("report", None, True, False)])

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

    def test_arm_check_runs_ping_then_status_and_closes_connection(self):
        created = []
        outcomes = {
            "ping": lifecycle("DONE", {"downstream_payload": "pong"}),
            "status": lifecycle("DONE", {"downstream_payload": "service_state=ready"}),
            "move_joint": lifecycle("REJECTED", {"error_code": "admission_rejected"}),
        }
        clients = []

        def factory(host, port, timeout, session_id):
            client = FakeArmClient(outcomes)
            created.append((host, port, timeout, session_id))
            clients.append(client)
            return client

        exit_code, output, _manager = run_cli(
            ["arm", "check", "--json", "--arm-host", "192.0.2.40", "--arm-port", "9000"],
            arm_client_factory=factory,
        )
        payload = json.loads(output)
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["operation"], "arm.check")
        self.assertEqual(payload["code"], "ok")
        self.assertEqual(created, [("192.0.2.40", 9000, 3.0, "robot-cli")])
        self.assertEqual(clients[0].calls, ["ping", "status"])
        self.assertTrue(clients[0].connection.closed)

    def test_arm_yolo_jog_commands_expose_signed_joint_and_xyz_deltas(self):
        outcomes = {
            "ping": lifecycle("DONE"), "status": lifecycle("DONE"),
            "move_joint": lifecycle("DONE"), "jog_joint": lifecycle("DONE"),
            "jog_xyz": lifecycle("DONE"),
        }
        clients = []
        def factory(*_args):
            client = FakeArmClient(outcomes)
            clients.append(client)
            return client

        exit_code, output, _ = run_cli(
            ["arm", "jog-joint", "--joint", "6", "--delta", "-2", "--speed", "8", "--accel", "7", "--json"],
            arm_client_factory=factory,
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(output)["operation"], "arm.jog-joint")
        self.assertEqual(clients[-1].calls, [("jog_joint", (0.0, 0.0, 0.0, 0.0, 0.0, -2.0), 7, 8)])

        exit_code, _output, _ = run_cli(
            ["arm", "jog-xyz", "--axis", "z", "--delta", "5", "--user", "1", "--tool", "2", "--json"],
            arm_client_factory=factory,
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(clients[-1].calls, [("jog_xyz", (0.0, 0.0, 5.0), 1, 2, 5, 5)])


if __name__ == "__main__":
    unittest.main()
