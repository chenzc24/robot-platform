"""Deterministic checkpoint orchestration for localized Baseline."""

import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/console"))

from drawing import (
    DrawingExecutionAdmission,
    RelocationAdmission,
    execute_drawing,
    execute_localized_drawing,
)
from drawing.config import parse_drawing_config
from drawing.control_modes import parse_drawing_control_config
from drawing.loader import parse_drawing_document


STATUS = (
    "service_state=ready;motion_enabled=1;control_mode=yolo;active_sequence=0;"
    "last_error=none;terminal_position_supported=0;cancel_supported=0;"
    "feedback_valid=1;feedback_error=none;joint_deg=1,2,3,4,5,6;"
    "pose=1,2,3,4,5,6;pose_user=0;pose_tool=0;sample_id=7;sample_time_ms=1234"
)


def done(name="arm.command"):
    return [{"lifecycle": "DONE", "name": name, "payload": {}}]


def status_done():
    return [{
        "version": 1, "kind": "lifecycle", "message_id": "reply",
        "sequence": 2, "target": "arm", "name": "arm.status", "ttl_ms": 0,
        "payload": {"downstream_sequence": 2, "terminal_position": "unknown", "downstream_payload": STATUS},
        "correlation_id": "request", "lifecycle": "DONE",
    }]


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Arm:
    def __init__(self):
        self.calls = []

    def ping(self):
        return done("arm.ping")

    def status(self):
        return status_done()

    def _move(self, name, *args, **kwargs):
        self.calls.append(name)
        return done()

    def move_joint(self, *args, **kwargs):
        return self._move("move_joint", *args, **kwargs)

    def jog_xyz(self, *args, **kwargs):
        return self._move("jog_xyz", *args, **kwargs)

    def draw_stroke(self, *args, **kwargs):
        return self._move("draw_stroke", *args, **kwargs)

    def gripper(self, *args, **kwargs):
        return self._move("gripper", *args, **kwargs)


class Chassis:
    def __init__(self):
        self.calls = []

    def velocity(self, *args):
        self.calls.append("velocity")

    def stop(self):
        self.calls.append("stop")

    def ping(self):
        self.calls.append("ping")

    def status(self):
        self.calls.append("status")
        return {
            "version": 3, "sequence": 9, "type": "STATE", "ttl_ms": 0,
            "payload": {
                "service_state": "ready", "chassis_state": "enabled_stopped",
                "motion_permitted": True, "authenticated": True,
                "hold_remaining_ms": 0, "last_error": "none",
            },
        }


class Localization:
    def __init__(self):
        self.generation = 2
        self.offset = 0.0
        self.requested = False
        self.polls = 0
        self.tasks = []

    def snapshot(self):
        if self.requested and self.polls == 0:
            self.polls += 1
            return {"state": "collecting", "generation": 2, "context": None}
        if self.requested:
            self.generation = 3
            self.offset = -35.0
            self.requested = False
        return {
            "state": "locked", "generation": self.generation,
            "context": {
                "generation": self.generation,
                "json_axis_offset_mm": self.offset,
                "json_mm_per_rail_mm": -1.0,
                "rail_position_mm": -self.offset,
                "source": {"min_confidence": 0.9},
            },
        }

    def begin_task(self, task_id, generation):
        self.tasks.append(("begin", task_id, generation))

    def finish_task(self, task_id, outcome, result):
        self.tasks.append(("finish", task_id, outcome))

    def on_motion_intent(self, reason):
        self.motion_reason = reason

    def on_chassis_status(self, state):
        self.stopped_state = state

    def request_relocalization(self):
        self.requested = True


def drawing_config():
    return parse_drawing_config({
        "production_ready": True, "flat_group_name": "red",
        "group_pen_slots": {"red": "P1"},
        "pen_rack": {
            "change_depth_mm": 60, "final_return_depth_mm": 30,
            "gripper_open_mm": 60, "gripper_closed_mm": 1,
            "slots": {name: {"joint_deg": [index] * 6}
                      for index, name in enumerate(("P1", "P2", "P3", "P4"), 1)},
        },
        "geometry": {
            "canvas_width_mm": 100, "canvas_height_mm": 80,
            "user_y_offset_mm": -50, "user_z_offset_mm": -40,
            "home_pose_user_y_mm": 0, "reachable_user_y_min_mm": -60,
            "reachable_user_y_max_mm": 40, "pen_travel_x_mm": 20,
            "home_joints_deg": [-120, 0, -90, -90, -30, 90],
            "user": 0, "tool": 0, "draw_speed_pct": 12,
            "draw_blend_pct": 100, "travel_speed_pct": 50, "accel_pct": 20,
        },
    })


def control_config(mode="localized_baseline", initial_offset=0):
    document = {
        "version": 2, "production_ready": True,
        "selected_mode": mode, "json_mm_per_rail_mm": -1.0,
        "baseline": {"initial_json_axis_offset_mm": initial_offset,
                     "speed_mm_s": 50, "refresh_ms": 100, "hold_ms": 250,
                     "max_distance_mm": 300, "settle_ms": 0},
        "localized_baseline": {"poll_ms": 100, "localization_timeout_ms": 1000},
        "advanced": {"poll_ms": 100, "station_timeout_ms": 1000,
                     "localization_timeout_ms": 1000},
    }
    return parse_drawing_control_config(document)


class LocalizedDrawingTests(unittest.TestCase):
    def test_baseline_uses_configured_initial_offset_and_resumes_checkpoint(self):
        job = parse_drawing_document({
            "version": "1.0", "coordinate_space": "normalized",
            "axis": {"origin": "top-left", "x_positive": "right", "y_positive": "down"},
            "canvas": {"width": 1, "height": 1, "source_width": 10,
                       "source_height": 10, "source_aspect_ratio": 1,
                       "target_width_mm": 100, "target_height_mm": 80},
            "strokes": [{"id": "s1", "order": 1,
                         "points": [[0, 0.25], [0.5, 0.5], [1, 0.75]],
                         "closed": False}],
        }, "red")
        clock, arm, chassis = Clock(), Arm(), Chassis()
        result = execute_drawing(
            arm, chassis, None, job, drawing_config(), control_config("baseline", 5),
            DrawingExecutionAdmission(True, True, True, True),
            RelocationAdmission(True, True, True, "enabled_stopped"),
            sleep_func=clock.sleep, clock=clock,
        )
        self.assertEqual(result["mode"], "baseline")
        self.assertEqual(result["windows"], 2)
        self.assertEqual(result["final_generation"], None)
        self.assertEqual(result["final_json_axis_offset_mm"], -35.0)
        self.assertEqual(result["relocations"][0]["offset_source"], "commanded_open_loop")
        self.assertEqual(result["relocations"][0]["json_axis_offset_delta_mm"], -40.0)
        self.assertIn("velocity", chassis.calls)

    def test_window_relocation_and_exact_checkpoint_resume(self):
        job = parse_drawing_document({
            "version": "1.0", "coordinate_space": "normalized",
            "axis": {"origin": "top-left", "x_positive": "right", "y_positive": "down"},
            "canvas": {"width": 1, "height": 1, "source_width": 10,
                       "source_height": 10, "source_aspect_ratio": 1,
                       "target_width_mm": 100, "target_height_mm": 80},
            "strokes": [{"id": "s1", "order": 1,
                         "points": [[0, 0.25], [0.5, 0.5], [1, 0.75]],
                         "closed": False}],
        }, "red")
        clock, arm, chassis, localization = Clock(), Arm(), Chassis(), Localization()
        result = execute_localized_drawing(
            arm, chassis, localization, job, drawing_config(), control_config(),
            DrawingExecutionAdmission(True, True, True, True),
            RelocationAdmission(True, True, True, "enabled_stopped"),
            "test", sleep_func=clock.sleep, clock=clock,
        )
        self.assertEqual(result["windows"], 2)
        self.assertEqual(len(result["relocations"]), 1)
        self.assertEqual(result["final_generation"], 3)
        self.assertEqual(result["final_json_axis_offset_mm"], -35.0)
        self.assertIn("velocity", chassis.calls)
        self.assertNotIn("line_follow_start", chassis.calls)
        self.assertEqual([item[0] for item in localization.tasks], [
            "begin", "finish", "begin", "finish",
        ])


if __name__ == "__main__":
    unittest.main()
