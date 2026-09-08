"""CLI tests proving the drawing task is preview-only."""

import importlib.util
import io
import json
import pathlib
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout


ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "drawing_task", ROOT / "app/drawing_task.py"
)
DRAWING_TASK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRAWING_TASK)


class DrawingTaskCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.temp.name)
        self.drawing = root / "drawing.json"
        self.config = root / "drawing.local.json"
        self.plan = root / "plan.json"
        self.drawing.write_text(
            json.dumps(
                {
                    "version": "1.0",
                    "coordinate_space": "normalized",
                    "axis": {"origin": "top-left", "x_positive": "right", "y_positive": "down"},
                    "canvas": {
                        "width": 1,
                        "height": 1,
                        "source_width": 10,
                        "source_height": 10,
                        "source_aspect_ratio": 1,
                        "target_width_mm": 210,
                        "target_height_mm": 210,
                    },
                    "strokes": [
                        {"id": "s1", "order": 1, "points": [[0, 0], [1, 1]], "closed": False}
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.config.write_text(
            json.dumps(
                {
                    "production_ready": False,
                    "flat_group_name": "default",
                    "group_pen_slots": {"default": "P1"},
                    "pen_rack": {
                        "change_depth_mm": 60,
                        "final_return_depth_mm": 30,
                        "gripper_open_mm": 60,
                        "gripper_closed_mm": 1,
                        "slots": {
                            "P1": {"joint_deg": [1, 2, 3, 4, 5, 6]},
                            "P2": {"joint_deg": [2, 3, 4, 5, 6, 7]},
                            "P3": {"joint_deg": [3, 4, 5, 6, 7, 8]},
                            "P4": {"joint_deg": [4, 5, 6, 7, 8, 9]}
                        }
                    },
                    "geometry": {
                        "canvas_width_mm": 100,
                        "canvas_height_mm": 100,
                        "user_y_offset_mm": -50,
                        "user_z_offset_mm": -50,
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
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_cli_exposes_no_execute_or_device_endpoint_option(self):
        destinations = {
            action.dest for action in DRAWING_TASK.argument_parser()._actions
        }
        self.assertNotIn("execute", destinations)
        self.assertNotIn("host", destinations)
        self.assertNotIn("port", destinations)

    def test_preview_reports_metadata_mismatch_and_writes_only_explicit_plan(self):
        output = io.StringIO()
        with redirect_stdout(output):
            result = DRAWING_TASK.main(
                [str(self.drawing), "--config", str(self.config), "--output-plan", str(self.plan)]
            )
        self.assertEqual(result, 0)
        self.assertTrue(self.plan.is_file())
        self.assertIn('"preview_only": true', output.getvalue())
        self.assertIn('"canvas_metadata_mm": [', output.getvalue())
        self.assertIn('"configured_canvas_mm": [', output.getvalue())
        self.assertIn("PREVIEW_ONLY no device modules loaded", output.getvalue())
        source = (ROOT / "app/drawing_task.py").read_text(encoding="utf-8")
        self.assertNotIn("maixcam_arm_client", source)
        self.assertNotIn("open_connection", source)

    def test_existing_output_and_invalid_checkpoint_fail_cleanly(self):
        self.plan.write_text("preserve", encoding="utf-8")
        errors = io.StringIO()
        with redirect_stderr(errors), redirect_stdout(io.StringIO()):
            result = DRAWING_TASK.main(
                [str(self.drawing), "--config", str(self.config), "--output-plan", str(self.plan)]
            )
        self.assertEqual(result, 2)
        self.assertEqual(self.plan.read_text(encoding="utf-8"), "preserve")

        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            result = DRAWING_TASK.main(
                [str(self.drawing), "--config", str(self.config), "--checkpoint", "9", "0", "0"]
            )
        self.assertEqual(result, 2)


if __name__ == "__main__":
    unittest.main()
