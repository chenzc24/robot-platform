"""Lifecycle and control-lease tests for the ESP32 runtime foundation."""

import json
import pathlib
import sys
import unittest


APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "esp32" / "app"
sys.path.insert(0, str(APP_DIR))

from application import Esp32Application
from control_lease import ControlLease, ControlLeaseError
from esp_runtime_status import RuntimeStatus


class FakeClock:
    def __init__(self, value=1_000):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, milliseconds):
        self.value += milliseconds


class ApplicationLifecycleTests(unittest.TestCase):
    def test_unsupported_mode_reports_rejection_and_stays_safe_idle(self):
        output = []
        status = RuntimeStatus(
            "esp32",
            "application",
            clock_ms=FakeClock(),
            output=output.append,
        )
        result = Esp32Application(requested_mode="ps2", status=status).run()
        events = [json.loads(line) for line in output]
        self.assertEqual(result, "safe_idle")
        self.assertEqual([event["event"] for event in events], [
            "application_starting",
            "run_mode_rejected",
        ])
        self.assertEqual(events[-1]["state"], "safe_idle")
        self.assertEqual(events[-1]["error_code"], "unsupported_run_mode")
        self.assertFalse(events[-1]["detail"]["motion_hardware_initialized"])

    def test_safe_idle_reports_ready_without_an_error(self):
        output = []
        status = RuntimeStatus(
            "esp32",
            "application",
            clock_ms=FakeClock(),
            output=output.append,
        )
        Esp32Application(requested_mode="safe_idle", status=status).run()
        event = json.loads(output[-1])
        self.assertEqual(event["event"], "application_ready")
        self.assertEqual(event["state"], "safe_idle")
        self.assertIsNone(event["error_code"])


class ControlLeaseTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.lease = ControlLease(clock_ms=self.clock)

    def test_only_one_owner_can_hold_the_lease(self):
        self.lease.acquire("console", 500)
        with self.assertRaises(ControlLeaseError):
            self.lease.acquire("ps2", 500)
        self.assertEqual(self.lease.status()["owner"], "console")

    def test_expiration_clears_owner_and_allows_a_new_owner(self):
        self.lease.acquire("console", 500)
        self.clock.advance(500)
        self.assertEqual(self.lease.expire_if_needed(), "console")
        self.lease.acquire("ps2", 500)
        self.assertEqual(self.lease.status()["owner"], "ps2")

    def test_only_the_owner_can_renew_or_release(self):
        self.lease.acquire("console", 500)
        with self.assertRaises(ControlLeaseError):
            self.lease.renew("other", 500)
        with self.assertRaises(ControlLeaseError):
            self.lease.release("other")
        self.lease.renew("console", 800)
        self.assertGreater(self.lease.status()["remaining_ms"], 0)
        self.lease.release("console")
        self.assertFalse(self.lease.status()["active"])

    def test_timeout_bounds_are_enforced(self):
        with self.assertRaises(ValueError):
            self.lease.acquire("console", 50)
        with self.assertRaises(ValueError):
            self.lease.acquire("console", 20_000)


if __name__ == "__main__":
    unittest.main()
