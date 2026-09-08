"""Coordinate and checkpoint tests for the no-device rehearsal simulator."""

import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "console"))

from drawing.config import parse_drawing_config
from drawing.loader import parse_drawing_document
from drawing.models import DrawingError
from drawing.simulator import simulate_localized_baseline


def drawing_config():
    return parse_drawing_config({
        "production_ready": False,
        "flat_group_name": "default",
        "group_pen_slots": {"default": "P1"},
        "pen_rack": {
            "change_depth_mm": 60,
            "final_return_depth_mm": 30,
            "gripper_open_mm": 60,
            "gripper_closed_mm": 1,
            "slots": {
                name: {"joint_deg": [index] * 6}
                for index, name in enumerate(("P1", "P2", "P3", "P4"), 1)
            },
        },
        "geometry": {
            "canvas_width_mm": 100,
            "canvas_height_mm": 80,
            "user_y_offset_mm": -50,
            "user_z_offset_mm": -40,
            "home_pose_user_y_mm": 0,
            "reachable_user_y_min_mm": -100,
            "reachable_user_y_max_mm": 100,
            "pen_travel_x_mm": 20,
            "home_joints_deg": [-120, 0, -90, -90, -30, 90],
            "user": 0,
            "tool": 0,
            "draw_speed_pct": 12,
            "draw_blend_pct": 100,
            "travel_speed_pct": 50,
            "accel_pct": 20,
        },
    })


def drawing_job():
    return parse_drawing_document({
        "version": "1.0",
        "coordinate_space": "normalized",
        "axis": {"origin": "top-left", "x_positive": "right", "y_positive": "down"},
        "canvas": {
            "width": 1,
            "height": 1,
            "source_width": 100,
            "source_height": 80,
            "source_aspect_ratio": 1.25,
            "target_width_mm": 210,
            "target_height_mm": 210,
        },
        "strokes": [{
            "id": "s1",
            "order": 1,
            "points": [[0, 0], [0.5, 0.5], [1, 1]],
            "closed": False,
        }],
    })


class LocalizedBaselineSimulatorTests(unittest.TestCase):
    def test_rehearses_two_windows_with_exact_offset_and_generation(self):
        result = simulate_localized_baseline(
            drawing_job(),
            drawing_config(),
            rail_reference_mm=0,
            json_mm_per_rail_mm=-1,
            reachable_min_mm=-60,
            reachable_max_mm=40,
        )
        self.assertTrue(result["simulation_only"])
        self.assertEqual(result["summary"]["windows"], 2)
        self.assertEqual(result["summary"]["relocations"], 1)
        self.assertEqual(result["summary"]["total_absolute_rail_travel_mm"], 35)
        self.assertEqual(result["summary"]["rail_direction_changes"], 0)
        first, second = result["windows"]
        self.assertEqual(first["checkpoint_end"], {
            "group_index": 0, "stroke_index": 0, "next_point_index": 2,
        })
        self.assertEqual(first["relocation"]["requested_json_axis_offset_delta_mm"], -35)
        self.assertEqual(first["relocation"]["simulated_direct_rail_move_mm"], 35)
        self.assertEqual(first["relocation"]["logical_stop_state"], "enabled_stopped")
        self.assertEqual(second["generation"], 2)
        self.assertEqual(second["rail_position_mm"], 35)
        self.assertEqual(second["json_axis_offset_mm"], -35)
        self.assertTrue(second["complete"])
        self.assertEqual(second["point_rank_start"], 2)
        self.assertEqual(second["point_rank_end_exclusive"], 3)

    def test_initial_position_uses_reference_difference_and_scale(self):
        result = simulate_localized_baseline(
            drawing_job(), drawing_config(), rail_reference_mm=20,
            initial_rail_position_mm=30, json_mm_per_rail_mm=-1,
        )
        self.assertEqual(result["windows"][0]["rail_delta_from_reference_mm"], 10)
        self.assertEqual(result["windows"][0]["json_axis_offset_mm"], -10)
        self.assertEqual(result["summary"]["windows"], 1)

    def test_rejects_zero_scale_invalid_reach_and_window_limit(self):
        with self.assertRaisesRegex(DrawingError, "must not be zero"):
            simulate_localized_baseline(
                drawing_job(), drawing_config(), json_mm_per_rail_mm=0
            )
        with self.assertRaisesRegex(DrawingError, "minimum must be below maximum"):
            simulate_localized_baseline(
                drawing_job(), drawing_config(), reachable_min_mm=10,
                reachable_max_mm=10,
            )
        with self.assertRaisesRegex(DrawingError, "window limit"):
            simulate_localized_baseline(
                drawing_job(), drawing_config(), reachable_min_mm=-60,
                reachable_max_mm=40, max_windows=1,
            )


if __name__ == "__main__":
    unittest.main()
