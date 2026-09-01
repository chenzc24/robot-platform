"""Tests for flat device discovery, relay management, and process protection."""

import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
DEV_TOOLS = ROOT / "tools" / "dev"
sys.path.insert(0, str(DEV_TOOLS))

from connection_manager import (
    CommandResult,
    ConnectionLock,
    ConnectionManager,
    OperationRefused,
    SystemRunner,
)


class FakeNetwork:
    def __init__(self):
        self.maixcam_ipv4 = "192.0.2.20"
        self.local_ipv4 = "192.0.2.10"
        self.open_ports = set()
        self.arp_matches = []
        self.scan_matches = []

    def resolve_ipv4(self, _host):
        return self.maixcam_ipv4

    def tcp_open(self, host, port, timeout=0.35):
        del timeout
        return (host, port) in self.open_ports

    def local_ipv4_for(self, _remote_ipv4):
        return self.local_ipv4

    def scan_port(self, _local_ipv4, _port, exclude=()):
        del exclude
        return list(self.scan_matches)

    def arp_candidates(self, _local_ipv4):
        return list(self.arp_matches)


class FakeRunner:
    def __init__(self):
        self.relay_running = False
        self.remote_video_start_succeeds = False
        self.network = None
        self.ssh_ready = True
        self.calls = []

    def run(self, args, timeout=10, input_text=None):
        self.calls.append((list(args), timeout, input_text))
        if "-Action" in args:
            action = args[args.index("-Action") + 1]
            if action == "status":
                return CommandResult(0 if self.relay_running else 1)
            if action == "start":
                self.relay_running = True
                return CommandResult(0, "VIDEO_RELAY_STARTED")
            if action == "stop":
                self.relay_running = False
                return CommandResult(0, "VIDEO_RELAY_STOPPED")
        if args[0] == "ssh" and args[-1] == "true":
            return CommandResult(0 if self.ssh_ready else 1)
        if args[0] == "ssh" and str(args[-1]).endswith("/start.sh"):
            if self.remote_video_start_succeeds:
                self.network.open_ports.add((self.network.maixcam_ipv4, 8554))
                return CommandResult(0, "RTSP_STARTED")
            return CommandResult(1, "", "RTSP_START_FAILED")
        return CommandResult(0, "OK")


class ConnectionManagerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.network = FakeNetwork()
        self.runner = FakeRunner()
        self.runner.network = self.network
        self.cache_path = pathlib.Path(self.temporary.name) / "connection.json"
        self.manager = ConnectionManager(
            runner=self.runner,
            network=self.network,
            cache_path=self.cache_path,
        )

    def make_all_links_ready(self):
        self.runner.relay_running = True
        self.network.open_ports.update(
            {
                ("192.0.2.30", 8266),
                ("192.0.2.20", 8554),
                ("127.0.0.1", 8555),
                ("127.0.0.1", 8889),
            }
        )

    def test_ready_report_has_only_four_flat_checks(self):
        self.make_all_links_ready()
        report = self.manager.report(explicit_esp32_host="192.0.2.30")
        self.assertEqual(report.level, "READY")
        self.assertEqual(
            [check.name for check in report.checks],
            ["maixcam", "esp32", "camera", "video"],
        )
        self.assertFalse(report.changed)

    def test_connect_starts_only_a_missing_local_relay(self):
        self.network.open_ports.update(
            {
                ("192.0.2.30", 8266),
                ("192.0.2.20", 8554),
                ("127.0.0.1", 8555),
                ("127.0.0.1", 8889),
            }
        )
        report = self.manager.report(
            explicit_esp32_host="192.0.2.30",
            ensure_relay=True,
        )
        self.assertEqual(report.level, "READY")
        self.assertTrue(report.changed)
        relay_actions = [
            call[0][call[0].index("-Action") + 1]
            for call in self.runner.calls
            if "-Action" in call[0]
        ]
        self.assertEqual(relay_actions, ["status", "start", "status"])

    def test_connect_does_not_start_relay_without_device_rtsp(self):
        self.network.open_ports.add(("192.0.2.30", 8266))
        report = self.manager.report(
            explicit_esp32_host="192.0.2.30",
            ensure_relay=True,
        )
        self.assertEqual(report.level, "DEGRADED")
        relay_actions = [
            call[0][call[0].index("-Action") + 1]
            for call in self.runner.calls
            if "-Action" in call[0]
        ]
        self.assertEqual(relay_actions, ["status"])

    def test_connect_starts_missing_device_video_then_local_relay(self):
        self.runner.remote_video_start_succeeds = True
        self.network.open_ports.update(
            {
                ("192.0.2.30", 8266),
                ("127.0.0.1", 8555),
                ("127.0.0.1", 8889),
            }
        )
        report = self.manager.report(
            explicit_esp32_host="192.0.2.30",
            ensure_relay=True,
        )
        self.assertEqual(report.level, "READY")
        self.assertTrue(report.changed)
        self.assertTrue(
            any(str(call[0][-1]).endswith("/start.sh") for call in self.runner.calls)
        )

    def test_esp32_discovery_rejects_multiple_webrepl_candidates(self):
        self.network.scan_matches = ["192.0.2.30", "192.0.2.31"]
        address, error = self.manager.discover_esp32(
            maixcam_ipv4=self.network.maixcam_ipv4
        )
        self.assertIsNone(address)
        self.assertEqual(error, "esp32_discovery_ambiguous")

    def test_esp32_discovery_prefers_an_active_arp_candidate(self):
        self.network.arp_matches = ["192.0.2.30", "192.0.2.31"]
        self.network.open_ports.add(("192.0.2.30", 8266))
        address, error = self.manager.discover_esp32(
            maixcam_ipv4=self.network.maixcam_ipv4
        )
        self.assertEqual(address, "192.0.2.30")
        self.assertIsNone(error)
        self.assertEqual(self.network.scan_matches, [])

    def test_remote_force_stop_script_checks_process_ownership(self):
        result = self.manager.remote_video_stop(force=True)
        self.assertEqual(result.returncode, 0)
        remote_script = self.runner.calls[-1][2]
        self.assertIn("/proc/$pid/cmdline", remote_script)
        self.assertIn("rtsp_server.py", remote_script)
        self.assertIn("kill -KILL", remote_script)
        self.assertNotIn("killall", remote_script)

    def test_connection_lock_rejects_an_overlapping_operation(self):
        lock_path = pathlib.Path(self.temporary.name) / "test.lock"
        with ConnectionLock(lock_path):
            with self.assertRaises(OperationRefused):
                with ConnectionLock(lock_path):
                    pass

    def test_system_runner_captures_output_without_a_shell(self):
        result = SystemRunner().run(
            [sys.executable, "-c", "print('runner-ready')"],
            timeout=3,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "runner-ready")
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
