"""Drawing math, fail-stop sequencing and the real protocol with fake device IO."""

import copy
import io
import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
for directory in ("app", "protocol", "src/console", "src/maixcam/arm", "src/robot_arm/runtime"):
    sys.path.insert(0, str(ROOT / directory))

import demo
from arm_motion_gateway import ArmMotionGateway
from arm_motion_service import ArmMotionService, ArmSafetyPolicy, DobotControllerApi
from command_service import ArmCommandService
from maixcam_arm_client import MaixCamArmClient, MaixCamArmUnknown


def document():
    return {
        "version": "1.0", "coordinate_space": "normalized",
        "axis": {"origin": "top-left", "x_positive": "right", "y_positive": "down"},
        "canvas": {"width": 1, "height": 1, "target_width_mm": 210, "target_height_mm": 210},
        "strokes": [{"id": "one", "order": 1, "points": [[0.3, 0.3], [0.5, 0.3], [0.5, 0.5], [0.3, 0.3]]}],
    }


class FakeConnection:
    """In-memory PC -> MaixCam -> RPA2 -> native API adapter round trip."""

    def __init__(self):
        self.calls, self.requests, self.pending = [], [], []
        self.closed = False
        self.fail_at = self.drop_at = self.interrupt_at = None

        def record(name):
            def call(*args):
                self.calls.append((name, args))
                if len(self.calls) == self.fail_at:
                    raise ValueError("injected_native_failure")
                if len(self.calls) == self.interrupt_at:
                    raise KeyboardInterrupt
            return call

        api = DobotControllerApi(
            lambda *_: 0, record("MovJ"), lambda *_: 0, record("MovL"),
            record("SetParallelGripper"), record("RelJointMovJ"), record("RelMovLUser"),
            lambda: [-120, 0, -90, -90, -30, 90], lambda *_: [10, 20, 30, 0, 0, 0],
        )
        self.controller = ArmMotionService(api, ArmSafetyPolicy(yolo_mode=True))
        self.service = ArmCommandService(ArmMotionGateway(self.requests.append), admission=lambda _: True)

    def send(self, data):
        output = self.service.feed_computer(data)
        for request in self.requests:
            replies, errors = self.controller.feed(request)
            assert not errors
            output += self.service.feed_uart(b"".join(replies))
        self.requests.clear()
        if len(self.calls) != self.drop_at:
            self.pending.append(output)
        return len(data)

    def recv(self, _size):
        if not self.pending:
            raise TimeoutError("injected_lost_reply")
        return self.pending.pop(0)

    def close(self):
        self.closed = True


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = pathlib.Path(self.temp.name) / "strokes.json"
        self.write(document())

    def write(self, data):
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def plan(self, config=None):
        return demo.build_plan(demo.load_strokes(self.path), config or demo.DrawingConfig())

    def run_offline(self, connection):
        sleep = mock.Mock()
        demo.run_plan(MaixCamArmClient(connection), self.plan(), sleep=sleep, report=lambda _: None)
        return sleep

    def test_entire_schema_and_all_points_checked(self):
        invalid = []
        for path, value in (("version", "2.0"), ("coordinate_space", "pixels"),
                            ("axis", {}), ("canvas", {}), ("strokes", {})):
            data = document()
            data[path] = value
            invalid.append(data)
        for point in ([float("nan"), 0.5], [float("inf"), 0], [True, 0],
                      ["0.3", 0.5], [-0.01, 0], [0, 1.01], [0, 0, 0], None):
            data = document()
            data["strokes"][0]["points"].append(point)
            invalid.append(data)
        data = document()
        data["strokes"].append(copy.deepcopy(data["strokes"][0]))
        invalid.append(data)
        for data in invalid:
            with self.subTest(data=data):
                self.write(data)
                with self.assertRaises(demo.DemoError):
                    demo.load_strokes(self.path)

    def test_order_sorting_keeps_points_duplicates_and_endpoints(self):
        data = document()
        data["strokes"][0]["points"].insert(1, [0.3, 0.3])
        second = {"order": 2, "points": [[0, 0], [1, 1]]}
        data["strokes"].insert(0, second)
        self.write(data)
        strokes = demo.load_strokes(self.path)
        self.assertEqual([s.order for s in strokes], [1, 2])
        self.assertEqual(strokes[0].points, tuple(map(tuple, data["strokes"][1]["points"])))
        self.assertEqual(strokes[1].points, ((0, 0), (1, 1)))

    def test_short_strokes_skipped_and_empty_job_sends_no_gripper(self):
        data = document()
        data["strokes"].extend([{"order": 2, "points": []}, {"order": 3, "points": [[0, 0]]}])
        self.write(data)
        self.assertEqual(sum(s.name == "arm.move_joint" for s in self.plan()), 1)
        data["strokes"].pop(0)
        self.write(data)
        with self.assertRaisesRegex(demo.DemoError, "no strokes"):
            self.plan()

    def test_original_geometry_reaches_native_api_without_frame_swapping(self):
        connection = FakeConnection()
        sleep = self.run_offline(connection)
        self.assertEqual(connection.calls[0], ("SetParallelGripper", (1,)))
        self.assertEqual(connection.calls[1], ("MovJ", (
            {"joint": [-120, 0, -90, -90, -30, 90]}, {"a": 5, "v": 5, "cp": 0})))
        expected = [[0, 0, 40], [-20, 0, 0], [0, 20, 0],
                    [0, 0, -20], [0, -20, 20], [20, 0, 0]]
        self.assertEqual(len(connection.calls), 8)
        for index, (name, (vector, options)) in enumerate(connection.calls[2:]):
            self.assertEqual(name, "RelMovLUser")
            for actual, wanted in zip(vector, expected[index] + [0, 0, 0]):
                self.assertAlmostEqual(actual, wanted)
            self.assertEqual(options, {"user": 0, "tool": 0, "a": 5,
                                      "v": 15 if index in (2, 3, 4) else 5, "r": 0})
        self.assertEqual(sleep.call_args_list, [mock.call(0.2), mock.call(0.3)])

    def test_configurable_geometry_and_frames_apply_to_every_translation(self):
        config = demo.DrawingConfig(canvas_mm=50, offset_y_mm=2, offset_z_mm=3,
                                    pen_travel_mm=4, user=2, tool=3, draw_speed=6,
                                    travel_speed=2, accel=3, gripper_mm=9)
        steps = self.plan(config)
        self.assertEqual(steps[0].payload, {"width_mm": 9})
        moves = [step.payload for step in steps if step.name == "arm.jog_xyz"]
        self.assertEqual(moves[0]["translation_mm"], [0, 17, 38])
        self.assertEqual(moves[1]["translation_mm"], [-4, 0, 0])
        self.assertEqual(moves[-1]["translation_mm"], [4, 0, 0])
        self.assertTrue(all(move["user"] == 2 and move["tool"] == 3 and move["accel_pct"] == 3 for move in moves))

    def test_each_stroke_homes_and_lifts_with_gripper_only_once(self):
        data = document()
        data["strokes"].append({"order": 2, "points": [[0.5, 0.5], [0.5, 0.6]]})
        self.write(data)
        steps = self.plan()
        self.assertEqual(sum(step.name == "arm.gripper" for step in steps), 1)
        homes = [i for i, step in enumerate(steps) if step.name == "arm.move_joint"]
        self.assertEqual(len(homes), 2)
        self.assertEqual(steps[homes[1] - 2].payload["translation_mm"], [20, 0, 0])
        self.assertEqual(steps[homes[1] + 2].payload["translation_mm"], [0, 20, 20])

    def test_invalid_configuration_and_derived_overflow_rejected(self):
        for values in ({"canvas_mm": 0}, {"offset_y_mm": float("nan")},
                       {"pen_travel_mm": -20}, {"user": True}, {"tool": 10},
                       {"draw_speed": 101}, {"travel_speed": 0}, {"gripper_mm": 71},
                       {"accel": 5.5}, {"home_joints": (0, 0)},
                       {"home_joints": (float("inf"), 0, 0, 0, 0, 0)}):
            with self.subTest(values=values), self.assertRaises(demo.DemoError):
                demo.DrawingConfig(**values)
        with self.assertRaises(demo.DemoError):
            self.plan(demo.DrawingConfig(canvas_mm=1.7e308, offset_y_mm=1.7e308))

    def test_fault_aborts_drawing_without_lift_home_or_retry(self):
        connection = FakeConnection()
        connection.fail_at = 5
        with self.assertRaisesRegex(demo.DemoError, "injected_native_failure"):
            self.run_offline(connection)
        self.assertEqual(len(connection.calls), 5)
        self.assertEqual(connection.calls[-1][0], "RelMovLUser")

    def test_lost_reply_aborts_without_replay_or_cleanup_motion(self):
        connection = FakeConnection()
        connection.drop_at = 5
        with self.assertRaises(MaixCamArmUnknown):
            self.run_offline(connection)
        self.assertEqual(len(connection.calls), 5)

    def test_keyboard_interrupt_never_generates_recovery_motion(self):
        connection = FakeConnection()
        connection.interrupt_at = 5
        with self.assertRaises(KeyboardInterrupt):
            self.run_offline(connection)
        self.assertEqual(len(connection.calls), 5)

    def test_unready_status_prevents_even_gripper_motion(self):
        for attribute, value in (("policy", ArmSafetyPolicy()), ("service_state", "fault"),
                                 ("active_sequence", 12), ("error_code", "native_fault")):
            connection = FakeConnection()
            setattr(connection.controller, attribute, value)
            with self.subTest(attribute=attribute), self.assertRaises(demo.DemoError):
                self.run_offline(connection)
            self.assertEqual(connection.calls, [])

    def test_non_done_and_malformed_terminals_do_not_advance(self):
        for response in (None, [], {}, [None], [{"lifecycle": "DONE"}],
                         [{"lifecycle": "RUNNING", "payload": {}}],
                         [{"lifecycle": "REJECTED", "payload": {"error_code": "denied"}}]):
            with self.subTest(response=response), self.assertRaises(demo.DemoError):
                demo.require_done(response, "test")

    def test_default_preview_never_opens_network_or_asks_for_confirmation(self):
        with mock.patch.object(demo, "open_connection") as connect, mock.patch("builtins.input") as prompt:
            with redirect_stdout(io.StringIO()) as output:
                result = demo.main([str(self.path)])
            self.assertEqual(result, 0)
            self.assertIn("PREVIEW ONLY", output.getvalue())
            self.assertIn("100 x 100", output.getvalue())
            connect.assert_not_called()
            prompt.assert_not_called()
        self.assertEqual(demo.argument_parser().parse_args([]).json_path, ROOT / "dataset/strokes_railway_new.json")

    def test_invalid_late_point_fails_before_connection(self):
        data = document()
        data["strokes"].append({"order": 2, "points": [[0, 0], [1, 3]]})
        self.write(data)
        with mock.patch.object(demo, "open_connection") as connect, redirect_stderr(io.StringIO()):
            self.assertEqual(demo.main([str(self.path), "--execute"]), 2)
            connect.assert_not_called()

    def test_cancelled_safety_prompt_does_not_connect(self):
        with mock.patch.object(demo, "open_connection") as connect, mock.patch("builtins.input", return_value=""):
            with redirect_stdout(io.StringIO()):
                result = demo.main([str(self.path), "--execute", "--host", "example.invalid", "--port", "8780"])
            self.assertEqual(result, 2)
            connect.assert_not_called()

    def test_cli_closes_connection_on_success_unknown_and_interrupt(self):
        for failure, expected in ((None, 0), (MaixCamArmUnknown("outcome_unknown"), 2), (KeyboardInterrupt(), 130)):
            connection = FakeConnection()
            with mock.patch.object(demo, "open_connection", return_value=connection) as connect:
                with mock.patch("builtins.input", return_value="DRAW"), mock.patch.object(demo, "run_plan", side_effect=failure):
                    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                        result = demo.main([str(self.path), "--execute", "--host", "example.invalid", "--port", "8780"])
                self.assertEqual(result, expected)
                self.assertTrue(connection.closed)
                connect.assert_called_once_with("example.invalid", 8780, 3.0)


if __name__ == "__main__":
    unittest.main()
