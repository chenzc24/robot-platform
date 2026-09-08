import pathlib
import sys
import unittest
from types import SimpleNamespace


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "console"))

from drawing.executor import (
    DrawingExecutionAdmission,
    DrawingExecutionError,
    execute_drawing_plan,
    execute_drawing_window,
    flatten_plan_steps,
    flatten_plan_window,
)
from drawing.models import DrawingPlan, PlanStep


def done(name="arm.command", downstream=""):
    return [{"lifecycle": "DONE", "name": name, "payload": {"downstream_payload": downstream}}]


STATUS = (
    "service_state=ready;motion_enabled=1;control_mode=yolo;active_sequence=0;"
    "last_error=none;terminal_position_supported=0;cancel_supported=0;"
    "feedback_valid=1;feedback_error=none;joint_deg=1,2,3,4,5,6;"
    "pose=1,2,3,4,5,6;pose_user=0;pose_tool=0;sample_id=7;sample_time_ms=1234"
)


def status_done():
    return [{
        "version": 1, "kind": "lifecycle", "message_id": "reply", "sequence": 2,
        "target": "arm", "name": "arm.status", "ttl_ms": 0,
        "payload": {"downstream_sequence": 2, "terminal_position": "unknown", "downstream_payload": STATUS},
        "correlation_id": "request", "lifecycle": "DONE",
    }]


def config(ready=True):
    return SimpleNamespace(
        production_ready=ready,
        geometry=SimpleNamespace(user=0, tool=0),
    )


def plan():
    return DrawingPlan("job", "config", 0.0, (
        PlanStep("pen.select", "pick", {"steps": [
            {"kind": "arm.move_joint", "joint_deg": [1] * 6, "accel_pct": 20, "speed_pct": 50},
            {"kind": "arm.gripper", "width_mm": 1},
        ]}),
        PlanStep("arm.relative", "draw", {
            "translation_mm": [0, 1, 2], "user": 0, "tool": 0,
            "accel_pct": 20, "speed_pct": 12, "blend_pct": 100,
        }),
        PlanStep("sleep", "pause", {"seconds": 0.2}),
    ), True, None, {"barriers": 0})


ADMISSION = DrawingExecutionAdmission(True, True, True, True)


class FakeClient:
    def __init__(self, fail_call=None):
        self.calls = []
        self.fail_call = fail_call

    def _motion(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        if self.fail_call == len(self.calls):
            return [{"lifecycle": "FAULT", "payload": {"error_code": "simulated_fault"}}]
        return done()

    def ping(self): return done("arm.ping")
    def status(self): return status_done()
    def move_joint(self, *args, **kwargs): return self._motion("move_joint", *args, **kwargs)
    def jog_xyz(self, *args, **kwargs): return self._motion("jog_xyz", *args, **kwargs)
    def gripper(self, *args, **kwargs): return self._motion("gripper", *args, **kwargs)


class DrawingExecutorTests(unittest.TestCase):
    def test_flattens_pen_steps_and_forwards_draw_blend(self):
        client, sleeps, events = FakeClient(), [], []
        result = execute_drawing_plan(client, plan(), config(), ADMISSION, events.append, sleeps.append)
        self.assertEqual(result, {"completed_commands": 3, "steps_total": 4})
        self.assertEqual(sleeps, [0.2])
        self.assertEqual(client.calls[-1][2]["blend_pct"], 100)
        self.assertEqual(events[-1]["event"], "execution_done")

    def test_fault_stops_all_later_commands_without_retry(self):
        client = FakeClient(fail_call=2)
        with self.assertRaisesRegex(DrawingExecutionError, "simulated_fault") as caught:
            execute_drawing_plan(client, plan(), config(), ADMISSION, sleep_func=lambda _: None)
        self.assertEqual(caught.exception.completed_commands, 1)
        self.assertEqual(len(client.calls), 2)

    def test_admission_and_production_ready_are_required_before_preflight(self):
        client = FakeClient()
        with self.assertRaisesRegex(DrawingExecutionError, "execution_admission_required"):
            execute_drawing_plan(client, plan(), config(), DrawingExecutionAdmission(False, True, True, True))
        with self.assertRaisesRegex(DrawingExecutionError, "drawing_not_production_ready"):
            execute_drawing_plan(client, plan(), config(False), ADMISSION)
        self.assertEqual(client.calls, [])

    def test_incomplete_plan_is_rejected(self):
        incomplete = DrawingPlan("job", "config", 0, (), False, object(), {})
        with self.assertRaisesRegex(ValueError, "complete_drawing_plan_required"):
            flatten_plan_steps(incomplete)

    def test_window_executes_only_verified_safe_prefix_before_barrier(self):
        checkpoint = SimpleNamespace(to_dict=lambda: {
            "group_index": 0, "stroke_index": 0, "next_point_index": 1,
        })
        incomplete = DrawingPlan("job", "config", 0, (
            PlanStep("arm.home", "safe", {
                "joint_deg": [1] * 6, "accel_pct": 20, "speed_pct": 50,
                "purpose": "reposition_safe_pose",
            }),
            PlanStep("reposition.required", "barrier", {}),
        ), False, checkpoint, {})
        client = FakeClient()
        result = execute_drawing_window(
            client, incomplete, config(), ADMISSION, sleep_func=lambda _: None
        )
        self.assertFalse(result["complete"])
        self.assertEqual(result["checkpoint"]["next_point_index"], 1)
        self.assertEqual([call[0] for call in client.calls], ["move_joint"])

        unsafe = DrawingPlan("job", "config", 0, (
            PlanStep("arm.relative", "still drawing", {}),
            PlanStep("reposition.required", "barrier", {}),
        ), False, checkpoint, {})
        with self.assertRaisesRegex(ValueError, "does_not_end_arm_safe"):
            flatten_plan_window(unsafe)


if __name__ == "__main__":
    unittest.main()
