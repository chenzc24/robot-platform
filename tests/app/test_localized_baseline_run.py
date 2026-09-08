"""CLI gates for the AprilTag/direct-drive drawing mode."""

import importlib.util
import io
import json
import pathlib
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout


ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "localized_baseline_run", ROOT / "app/localized_baseline_run.py"
)
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class LocalizedBaselineRunCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        folder = pathlib.Path(self.temp.name)
        self.drawing = folder / "drawing.json"
        self.drawing_config = folder / "drawing.local.json"
        self.control_config = folder / "control.local.json"
        self.drawing.write_text(json.dumps({
            "version": "1.0", "coordinate_space": "normalized",
            "axis": {"origin": "top-left", "x_positive": "right", "y_positive": "down"},
            "canvas": {"width": 1, "height": 1, "source_width": 10,
                       "source_height": 10, "source_aspect_ratio": 1,
                       "target_width_mm": 100, "target_height_mm": 100},
            "strokes": [{"id": "s1", "order": 1,
                         "points": [[0, 0], [1, 1]], "closed": False}],
        }), encoding="utf-8")
        self.drawing_config.write_text(json.dumps({
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
                         "draw_blend_pct": 100, "travel_speed_pct": 50,
                         "accel_pct": 20},
        }), encoding="utf-8")
        self.control_config.write_text(json.dumps({
            "version": 2, "production_ready": False,
            "selected_mode": "localized_baseline", "json_mm_per_rail_mm": -1,
            "baseline": {"speed_mm_s": 50, "refresh_ms": 100,
                         "hold_ms": 250, "max_distance_mm": 300, "settle_ms": 2000},
            "localized_baseline": {"poll_ms": 100, "localization_timeout_ms": 10000},
            "advanced": {"poll_ms": 100, "station_timeout_ms": 30000,
                         "localization_timeout_ms": 10000},
        }), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def command(self, *extra):
        return [str(self.drawing), "--drawing-config", str(self.drawing_config),
                "--control-config", str(self.control_config), *extra]

    def test_default_dry_run_never_loads_runtime_or_opens_devices(self):
        original = RUNNER.load_runtime_config
        RUNNER.load_runtime_config = lambda *_: self.fail("dry-run loaded runtime")
        try:
            output = io.StringIO()
            with redirect_stdout(output):
                result = RUNNER.main(self.command())
            self.assertEqual(result, 0)
            self.assertIn('"mode": "localized_baseline"', output.getvalue())
            self.assertIn("DRY_RUN no device connection or motion", output.getvalue())
        finally:
            RUNNER.load_runtime_config = original

    def test_execute_requires_exact_hash_before_runtime_access(self):
        error = io.StringIO()
        with redirect_stderr(error), redirect_stdout(io.StringIO()):
            result = RUNNER.main(self.command("--execute"))
        self.assertEqual(result, 2)
        self.assertIn("job_hash_confirmation_required", error.getvalue())


if __name__ == "__main__":
    unittest.main()
