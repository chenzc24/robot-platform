"""Fault foundation across HTTP/runtime/client/MaixCam/controller, offline."""

import json
import pathlib
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/robot_arm"))
from test_arm_fault_foundation import Rig
from test_arm_web_integration import OfflineConnection
from test_web_console import config
from maixcam_arm_client import MaixCamArmClient, MaixCamArmUnknown
from web_console.runtime import WebConsoleError, WebConsoleRuntime
from web_console.server import create_server
from motion_link import decode_frame
from command_service import ArmCommandService
from arm_motion_gateway import ArmMotionGateway
from control_envelope import EnvelopeStreamDecoder, encode_message


class ArmFaultWebTests(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.controller = self.rig.service(True)
        self.connection = OfflineConnection(self.controller)
        self.client = MaixCamArmClient(self.connection)
        self.clock = [10.0]
        self.runtime = WebConsoleRuntime(config(), arm_factory=lambda _: self.client,
                                         start_workers=False, clock=lambda: self.clock[0])
        self.runtime.connect_arm()

    def tearDown(self):
        self.runtime.close()

    def test_specific_error_and_both_timestamps_reach_ui_and_persistent_log(self):
        with tempfile.TemporaryDirectory() as directory:
            log = pathlib.Path(directory) / "fault.log"
            self.runtime._event_log_path = log
            self.rig.check = 26
            with self.assertRaisesRegex(WebConsoleError, "path_check_rejected"):
                self.runtime.arm_command("jog_xyz", {"translation_mm": [1, 0, 0], "user": 2, "tool": 3})
            state = self.runtime.snapshot()
            evidence = state["faults"][0]["evidence"]
            self.assertEqual(evidence["vendor_code"], 26)
            self.assertEqual(evidence["vendor_api"], "CheckMovL")
            self.assertEqual(evidence["sample_time_ms"], 1234)
            self.assertEqual(evidence["raw_text"], "26")
            self.assertIn("received_at", evidence)
            self.assertEqual(state["events"][0]["evidence"], evidence)
            self.assertIn('"vendor_code": 26', log.read_text(encoding="utf-8"))
            self.assertFalse(any(call[0] == "motion" for call in self.rig.calls))
            self.runtime._event_log_path = None

    def test_ack_is_not_controller_clear_and_diagnostics_do_not_rearm_it(self):
        self.rig.check = 26
        with self.assertRaises(WebConsoleError):
            self.runtime.arm_command("jog_xyz", {"translation_mm": [1, 0, 0]})
        code = self.runtime.snapshot()["faults"][0]["code"]
        self.runtime.acknowledge_fault(code)
        self.runtime.arm_diagnostics()
        state = self.runtime.snapshot()
        self.assertTrue(state["faults"][0]["acknowledged"])
        self.assertEqual(state["arm"]["fault_diagnostics"]["controller"]["raw_text"], "[26]")
        self.assertEqual(self.rig.clear_count, 0)
        self.clock[0] = 16
        stale = self.runtime.snapshot()["arm"]["fault_diagnostics"]["controller"]
        self.assertFalse(stale["fresh"])
        self.assertEqual(stale["age_ms"], 6000)

    def test_clear_preserves_history_and_before_after_evidence_without_recovery(self):
        self.controller.service_state = "fault"
        state = self.runtime.arm_recovery("clear_errors", True)
        self.assertEqual(self.rig.clear_count, 1)
        self.assertEqual(state["arm"]["reported_state"], "fault")
        result = next(event for event in state["events"] if event["command"] == "clear_errors")
        self.assertEqual(result["evidence"]["before_raw_text"], "[26]")
        self.assertEqual(result["evidence"]["raw_text"], "[]")
        self.assertEqual(result["evidence"]["clear_vendor_code"], "0")
        self.runtime.arm_recovery("recover_service", True)
        self.assertEqual(self.runtime.snapshot()["arm"]["reported_state"], "ready")
        self.assertEqual(self.rig.clear_count, 1)
        self.assertFalse(any(call[0] == "motion" for call in self.rig.calls))

    def test_unsupported_clear_never_reaches_controller_and_is_not_success(self):
        self.controller.fault_access.read = None
        self.controller.fault_access.clear = None
        state = self.runtime.arm_diagnostics()
        self.assertFalse(state["arm"]["fault_capabilities"]["controller_clear"])
        self.assertFalse(state["arm"]["fault_diagnostics"]["controller"]["supported"])
        before = len(self.connection.trace)
        with self.assertRaisesRegex(WebConsoleError, "controller_clear_unsupported"):
            self.runtime.arm_recovery("clear_errors", True)
        self.assertEqual(len(self.connection.trace), before + 1)  # CAPS only
        self.assertEqual(self.rig.clear_count, 0)
        self.assertEqual(self.runtime.snapshot()["arm"]["recovery_result"], "unsupported")

    def test_recovery_rechecks_capability_and_requires_strict_confirmation(self):
        for value in (False, 1, "true", None):
            before = len(self.connection.trace)
            with self.assertRaisesRegex(WebConsoleError, "confirmation_required"):
                self.runtime.arm_recovery("clear_errors", value)
            self.assertEqual(len(self.connection.trace), before)
        self.runtime.arm_diagnostics()
        self.controller.fault_access.clear = None
        with self.assertRaisesRegex(WebConsoleError, "controller_clear_unsupported"):
            self.runtime.arm_recovery("clear_errors", True)
        self.assertEqual(self.rig.clear_count, 0)

    def test_recovery_in_progress_rejects_motion_and_another_recovery(self):
        entered, release = threading.Event(), threading.Event()
        failures = []
        original_clear = self.controller.fault_access.clear
        def clear():
            entered.set()
            if not release.wait(2): raise RuntimeError("test_clear_deadlock")
            return original_clear()
        self.controller.fault_access.clear = clear
        def recover():
            try: self.runtime.arm_recovery("clear_errors", True)
            except Exception as error: failures.append(error)
        worker = threading.Thread(target=recover); worker.start()
        try:
            self.assertTrue(entered.wait(1))
            with self.assertRaisesRegex(WebConsoleError, "arm_recovery_in_progress"):
                self.runtime.arm_command("jog_xyz", {"translation_mm": [1, 0, 0]})
            with self.assertRaisesRegex(WebConsoleError, "arm_request_in_flight"):
                self.runtime.arm_recovery("recover_service", True)
        finally:
            release.set(); worker.join(2)
        self.assertEqual(failures, [])
        self.assertFalse(any(call[0] == "motion" for call in self.rig.calls))

    def test_persisting_alarm_is_fault_not_done_and_remains_visible(self):
        self.rig.persist = True
        with self.assertRaisesRegex(WebConsoleError, "controller_alarm_persists"):
            self.runtime.arm_recovery("clear_errors", True)
        state = self.runtime.snapshot()
        self.assertEqual(state["events"][0]["lifecycle"], "FAULT")
        self.assertEqual(state["arm"]["recovery_result"], "unconfirmed")
        self.assertEqual(state["arm"]["gateway"], "online")

    def test_lost_clear_reply_is_unknown_and_never_retried(self):
        original_send = self.connection.send
        def send(data):
            if b'"name":"arm.clear_errors"' in data:
                self.connection.drop_reply = True
            return original_send(data)
        self.connection.send = send
        with self.assertRaises(WebConsoleError):
            self.runtime.arm_recovery("clear_errors", True)
        state = self.runtime.snapshot()
        self.assertEqual(self.rig.clear_count, 1)
        self.assertEqual(state["events"][0]["lifecycle"], "UNKNOWN")
        self.assertEqual(state["arm"]["recovery_result"], "unconfirmed")

    def test_partial_recovery_uart_write_is_unknown_not_rejected(self):
        writes = []
        def partial(frame):
            writes.append(frame)
            return len(frame) - 1
        service = ArmCommandService(ArmMotionGateway(partial))
        message = {"version": 1, "kind": "command", "message_id": "clear-1", "sequence": 1,
                   "target": "arm", "name": "arm.clear_errors", "ttl_ms": 1000, "payload": {"confirm": True}}
        responses = EnvelopeStreamDecoder().feed(service.feed_computer(encode_message(message)))[0]
        self.assertEqual(responses[-1]["lifecycle"], "UNKNOWN")
        self.assertEqual(len(writes), 1)

    def test_http_missing_confirmation_is_400_without_any_device_request(self):
        server = create_server(self.runtime, port=0)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        base = "http://127.0.0.1:%d" % server.server_address[1]
        before = len(self.connection.trace)
        try:
            request = urllib.request.Request(base + "/api/arm/recovery",
                data=json.dumps({"action": "clear_errors"}).encode(),
                headers={"Content-Type": "application/json", "Origin": base})
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(request, timeout=2)
            self.assertEqual(raised.exception.code, 400)
            self.assertFalse(json.load(raised.exception)["ok"])
            self.assertEqual(len(self.connection.trace), before)
        finally:
            server.shutdown(); server.server_close(); worker.join(2)


if __name__ == "__main__":
    unittest.main()
