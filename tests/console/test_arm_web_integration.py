"""Web-to-controller regression coverage with no hardware or vendor motion IO."""

import json
import pathlib
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
for path in ("protocol", "src/console", "src/maixcam/arm", "src/robot_arm/runtime"):
    sys.path.insert(0, str(ROOT / path))

from arm_motion_service import ArmMotionService, ArmSafetyPolicy
from arm_motion_gateway import ArmMotionGateway
from command_service import ArmCommandService
from maixcam_arm_client import MaixCamArmClient
from motion_link import decode_frame
from test_web_console import FakeArm, FakeChassis, config
from web_console.runtime import WebConsoleError, WebConsoleRuntime
from web_console.server import create_server


CASES = (
    ("jog_joint", {"joint_delta_deg": [2, 0, 0, 0, 0, 0]}),
    ("jog_xyz", {"translation_mm": [5, 0, 0], "user": 0, "tool": 0}),
    ("move_joint", {"joint_deg": [-88, 0, -140, -40, 0, 0]}),
    ("move_linear", {"pose": [-145.8, -102.846, 130.633, 90, 0, -90], "user": 0, "tool": 0}),
    ("gripper", {"width_mm": 28}),
)


class RecordingApi:
    def __init__(self):
        self.calls = []
        self.failure = None

    def read_feedback(self, user, tool):
        return (-90, 0, -140, -40, 0, 0), (-150.8, -102.846, 130.633, 90, 0, -90)

    def __getattr__(self, name):
        if name not in {item[0] for item in CASES}:
            raise AttributeError(name)

        def record(*args):
            self.calls.append((name, args))
            if self.failure is not None:
                raise self.failure

        return record


class OfflineConnection:
    def __init__(self, controller):
        self.controller = controller
        self.requests, self.pending, self.trace = [], [], []
        self.closed = self.drop_reply = False
        self.gateway = ArmCommandService(ArmMotionGateway(self.requests.append), admission=lambda _: True)

    def send(self, data):
        output = self.gateway.feed_computer(data)
        for wire in self.requests:
            replies, errors = self.controller.feed(wire)
            assert not errors
            self.trace.append((decode_frame(wire), [decode_frame(reply) for reply in replies]))
            output += self.gateway.feed_uart(b"".join(replies))
        self.requests.clear()
        if not self.drop_reply:
            self.pending.append(output)
        return len(data)

    def recv(self, size):
        if not self.pending:
            raise TimeoutError("test reply lost")
        return self.pending.pop(0)

    def close(self):
        self.closed = True


class ArmWebIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.api = RecordingApi()
        self.controller = ArmMotionService(self.api, ArmSafetyPolicy(yolo_mode=True))
        self.connection = OfflineConnection(self.controller)
        self.client = MaixCamArmClient(self.connection, "offline-regression")
        self.chassis = FakeChassis()
        self.runtime = WebConsoleRuntime(
            config(), chassis_factory=lambda _: self.chassis,
            arm_factory=lambda _: self.client, start_workers=False,
        )
        self.runtime.connect_arm()

    def tearDown(self):
        self.runtime.close()

    def test_all_five_commands_reach_controller_api_with_integer_wire_fields(self):
        for command, payload in CASES:
            with self.subTest(command=command):
                before = len(self.api.calls)
                state = self.runtime.arm_command(command, dict(payload, accel_pct=20.0, speed_pct=20.0))
                request, replies = self.connection.trace[-1]
                wire = request["payload"]
                if command == "gripper":
                    self.assertEqual(wire, "width_mm=28")
                else:
                    self.assertIn("accel_pct=20;speed_pct=20;", wire)
                self.assertEqual(replies[-1]["type"], "DONE")
                self.assertEqual(len(self.api.calls), before + 1)
                self.assertEqual(self.api.calls[-1][0], command)
                self.assertEqual(state["events"][0]["lifecycle"], "DONE")
                self.assertEqual(state["faults"], [])
        self.assertEqual(self.runtime.snapshot()["chassis"]["link"], "offline")

    def test_integral_boundaries_keep_full_ranges_and_real_valued_coordinates(self):
        for accel, speed in ((1, 100), (100.0, 1.0)):
            self.runtime.arm_command("jog_joint", {"joint_delta_deg": [0.25, 0, 0, 0, 0, 0], "accel_pct": accel, "speed_pct": speed})
            values, actual_accel, actual_speed = self.api.calls[-1][1]
            self.assertEqual(values[0], 0.25)
            self.assertIs(type(actual_accel), int)
            self.assertIs(type(actual_speed), int)
        for width in (0, 70.0):
            self.runtime.arm_command("gripper", {"width_mm": width})
            self.assertIs(type(self.api.calls[-1][1][0]), int)
            self.assertEqual(self.api.calls[-1][1][0], width)

    def test_fractional_nonfinite_boolean_and_out_of_range_fields_never_dispatch(self):
        for field in ("accel_pct", "speed_pct", "width_mm"):
            values = (20.5, float("nan"), float("inf"), float("-inf"), True, "20", None, -1, 101)
            for value in values:
                with self.subTest(field=field, value=value):
                    command = "gripper" if field == "width_mm" else "jog_joint"
                    payload = {field: value, "joint_delta_deg": [2, 0, 0, 0, 0, 0]}
                    before = len(self.connection.trace)
                    with self.assertRaises(WebConsoleError) as raised:
                        self.runtime.arm_command(command, payload)
                    self.assertEqual(raised.exception.http_status, 400)
                    self.assertEqual(len(self.connection.trace), before)
                    self.assertEqual(self.api.calls, [])

    def test_controller_fault_is_not_done_and_keeps_independent_links(self):
        self.runtime.connect_chassis()
        self.api.failure = ValueError("joint_path_rejected")
        with self.assertRaisesRegex(WebConsoleError, "joint_path_rejected"):
            self.runtime.arm_command("jog_joint", CASES[0][1])
        state = self.runtime.snapshot()
        self.assertEqual(state["events"][0]["lifecycle"], "FAULT")
        self.assertEqual(state["events"][0]["result"], "joint_path_rejected")
        self.assertEqual(state["faults"][0]["summary"], "joint_path_rejected")
        self.assertEqual(state["arm"]["last_error"], "joint_path_rejected")
        self.assertEqual(state["arm"]["gateway"], "online")
        self.assertEqual(state["chassis"]["link"], "online")
        self.assertFalse(self.connection.closed)
        self.assertEqual(len(self.api.calls), 1)
        self.runtime.chassis_health_once()
        self.assertIn(("ping",), self.chassis.calls)
        self.api.failure = None
        self.runtime.arm_command("jog_joint", CASES[0][1])
        self.assertEqual(len(self.api.calls), 2)

    def test_gateway_rejection_surfaces_as_rejected_without_controller_write(self):
        self.connection.gateway.admission = lambda _: False
        before = len(self.connection.trace)
        with self.assertRaisesRegex(WebConsoleError, "admission_rejected"):
            self.runtime.arm_command("jog_joint", CASES[0][1])
        state = self.runtime.snapshot()
        self.assertEqual(state["events"][0]["lifecycle"], "REJECTED")
        self.assertEqual(state["faults"][0]["summary"], "admission_rejected")
        self.assertEqual(len(self.connection.trace), before)
        self.assertFalse(self.connection.closed)

    def test_status_error_is_retained_without_log_flood_or_ack_reset(self):
        with tempfile.TemporaryDirectory() as folder:
            self.runtime._event_log_path = pathlib.Path(folder) / "events.log"
            self.controller.error_code = "invalid_gripper"
            self.runtime.refresh_arm_status(journal=False)
            code = self.runtime.snapshot()["faults"][0]["code"]
            self.runtime.acknowledge_fault(code)
            for _ in range(3):
                self.runtime.refresh_arm_status(journal=False)
            self.assertTrue(self.runtime.snapshot()["faults"][0]["acknowledged"])
            self.controller.error_code = None
            self.runtime.refresh_arm_status(journal=False)
            state = self.runtime.snapshot()
            self.assertEqual(state["arm"]["last_error"], "none")
            self.assertEqual(len(state["faults"]), 1)
            log = self.runtime._event_log_path.read_text(encoding="utf-8")
            self.assertEqual(log.count("FAULT source=arm"), 1)
            self.runtime._event_log_path = None

    def test_repeated_failed_operator_command_rearms_ack_and_logs_actual_fault(self):
        self.api.failure = ValueError("joint_path_rejected")
        with self.assertRaises(WebConsoleError):
            self.runtime.arm_command("jog_joint", CASES[0][1])
        self.runtime.acknowledge_fault(self.runtime.snapshot()["faults"][0]["code"])
        with self.assertRaises(WebConsoleError):
            self.runtime.arm_command("jog_joint", CASES[0][1])
        self.assertFalse(self.runtime.snapshot()["faults"][0]["acknowledged"])

    def test_lost_motion_reply_is_unknown_never_retried(self):
        self.runtime.connect_chassis()
        self.connection.drop_reply = True
        with self.assertRaisesRegex(WebConsoleError, "outcome_unknown"):
            self.runtime.arm_command("jog_joint", CASES[0][1])
        state = self.runtime.snapshot()
        self.assertEqual(len(self.api.calls), 1)
        self.assertEqual(state["events"][0]["lifecycle"], "UNKNOWN")
        self.assertEqual(state["arm"]["gateway"], "offline")
        self.assertEqual(state["chassis"]["link"], "online")
        self.assertTrue(self.connection.closed)

    def test_missing_malformed_and_nonterminal_responses_are_not_success(self):
        for reply in (None, [], {}, [None], [{"lifecycle": "DONE"}],
                      [{"lifecycle": "RUNNING", "payload": {}}],
                      [{"lifecycle": "UNKNOWN", "payload": {"error_code": "outcome_unknown"}}]):
            with self.subTest(reply=reply):
                arm = FakeArm()
                arm.jog_joint = lambda *_: reply
                runtime = WebConsoleRuntime(config(), arm_factory=lambda _: arm, start_workers=False)
                try:
                    runtime.connect_arm()
                    with self.assertRaises(WebConsoleError):
                        runtime.arm_command("jog_joint", CASES[0][1])
                    self.assertEqual(runtime.snapshot()["events"][0]["lifecycle"], "UNKNOWN")
                    self.assertTrue(arm.connection.closed)
                finally:
                    runtime.close()

    def test_fault_status_poll_keeps_link_without_logging_false_done(self):
        arm = FakeArm()
        runtime = WebConsoleRuntime(config(), arm_factory=lambda _: arm, start_workers=False)
        try:
            runtime.connect_arm()
            arm.status_result = [{"lifecycle": "FAULT", "payload": {"error_code": "feedback_unavailable"}}]
            with self.assertRaisesRegex(WebConsoleError, "feedback_unavailable"):
                runtime.refresh_arm_status()
            state = runtime.snapshot()
            self.assertEqual(state["events"][0]["lifecycle"], "FAULT")
            self.assertEqual(state["faults"][0]["summary"], "feedback_unavailable")
            self.assertFalse(arm.connection.closed)
        finally:
            runtime.close()

    def test_http_controller_failure_returns_error_and_fault_state(self):
        self.api.failure = ValueError("joint_path_rejected")
        server = create_server(self.runtime, port=0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = "http://127.0.0.1:%d" % server.server_address[1]
        request = urllib.request.Request(
            base + "/api/arm/command",
            data=json.dumps({"command": "jog_joint", "payload": CASES[0][1]}).encode(),
            headers={"Content-Type": "application/json", "Origin": base},
        )
        try:
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(request, timeout=2)
            self.assertEqual(raised.exception.code, 409)
            response = json.load(raised.exception)
            self.assertFalse(response["ok"])
            self.assertEqual(response["error"], "joint_path_rejected")
            self.assertEqual(response["state"]["events"][0]["lifecycle"], "FAULT")
            self.assertEqual(response["state"]["faults"][0]["summary"], "joint_path_rejected")
        finally:
            server.shutdown()
            server.server_close()
            worker.join(2)


if __name__ == "__main__":
    unittest.main()
