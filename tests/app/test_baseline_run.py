"""CLI safety gates for the arm-only Baseline executor."""

import importlib.util
import io
import json
import pathlib
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout


ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("baseline_run", ROOT / "app/baseline_run.py")
BASELINE_RUN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASELINE_RUN)


class BaselineRunCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        folder = pathlib.Path(self.temp.name)
        self.drawing = folder / "drawing.json"
        self.config = folder / "drawing.json.local"
        self.drawing.write_text(json.dumps({
            "version": "1.0", "coordinate_space": "normalized",
            "axis": {"origin": "top-left", "x_positive": "right", "y_positive": "down"},
            "canvas": {"width": 1, "height": 1, "source_width": 10, "source_height": 10,
                       "source_aspect_ratio": 1, "target_width_mm": 100, "target_height_mm": 100},
            "strokes": [{"id": "s1", "order": 1, "points": [[0, 0], [1, 1]], "closed": False}],
        }), encoding="utf-8")
        self.config.write_text(json.dumps({
            "production_ready": False, "flat_group_name": "default",
            "group_pen_slots": {"default": "P1"},
            "pen_rack": {"change_depth_mm": 60, "final_return_depth_mm": 30,
                         "gripper_open_mm": 60, "gripper_closed_mm": 1,
                         "slots": {name: {"joint_deg": [index] * 6}
                                   for index, name in enumerate(("P1", "P2", "P3", "P4"), 1)}},
            "geometry": {"canvas_width_mm": 100, "canvas_height_mm": 100,
                         "user_y_offset_mm": -50, "user_z_offset_mm": -50,
                         "home_pose_user_y_mm": 0, "reachable_user_y_min_mm": -100,
                         "reachable_user_y_max_mm": 100, "pen_travel_x_mm": 20,
                         "home_joints_deg": [-120, 0, -90, -90, -30, 90],
                         "user": 0, "tool": 0, "draw_speed_pct": 12,
                         "draw_blend_pct": 100, "travel_speed_pct": 50, "accel_pct": 20},
        }), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_default_is_dry_run_and_never_opens_connection(self):
        original = BASELINE_RUN.open_connection
        BASELINE_RUN.open_connection = lambda *_: self.fail("dry-run opened device connection")
        try:
            output = io.StringIO()
            with redirect_stdout(output):
                result = BASELINE_RUN.main([str(self.drawing), "--config", str(self.config)])
            self.assertEqual(result, 0)
            self.assertIn("DRY_RUN no device connection or motion", output.getvalue())
            self.assertIn('"chassis_commands": 0', output.getvalue())
        finally:
            BASELINE_RUN.open_connection = original

    def test_execute_rejects_hash_log_admission_and_false_production_gate(self):
        for extra, code in (
            (["--execute"], "job_hash_confirmation_required"),
            (["--execute", "--confirm-job-sha256", "wrong"], "job_hash_confirmation_required"),
        ):
            errors = io.StringIO()
            with redirect_stderr(errors), redirect_stdout(io.StringIO()):
                result = BASELINE_RUN.main([str(self.drawing), "--config", str(self.config), *extra])
            self.assertEqual(result, 2)
            self.assertIn(code, errors.getvalue())


if __name__ == "__main__":
    unittest.main()
