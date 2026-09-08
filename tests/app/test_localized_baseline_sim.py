"""CLI tests for the self-contained Localized Baseline rehearsal report."""

import importlib.util
import io
import json
import pathlib
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout


ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "localized_baseline_sim", ROOT / "app" / "localized_baseline_sim.py"
)
SIM = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SIM)


class LocalizedBaselineSimCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        folder = pathlib.Path(self.temp.name)
        self.drawing = folder / "drawing.json"
        self.config = folder / "drawing.json.config"
        self.control_config = folder / "drawing-control.json"
        self.output = folder / "rehearsal.html"
        self.drawing.write_text(json.dumps({
            "version": "1.0", "coordinate_space": "normalized",
            "axis": {"origin": "top-left", "x_positive": "right", "y_positive": "down"},
            "canvas": {"width": 1, "height": 1, "source_width": 10,
                       "source_height": 10, "source_aspect_ratio": 1,
                       "target_width_mm": 210, "target_height_mm": 210},
            "strokes": [{"id": "s1", "order": 1,
                         "points": [[0, 0], [0.5, 0.5], [1, 1]], "closed": False}],
        }), encoding="utf-8")
        self.config.write_text(json.dumps({
            "production_ready": False, "flat_group_name": "default",
            "group_pen_slots": {"default": "P1"},
            "pen_rack": {"change_depth_mm": 60, "final_return_depth_mm": 30,
                         "gripper_open_mm": 60, "gripper_closed_mm": 1,
                         "slots": {name: {"joint_deg": [index] * 6}
                                   for index, name in enumerate(("P1", "P2", "P3", "P4"), 1)}},
            "geometry": {"canvas_width_mm": 100, "canvas_height_mm": 80,
                         "user_y_offset_mm": -50, "user_z_offset_mm": -40,
                         "home_pose_user_y_mm": 0, "reachable_user_y_min_mm": -100,
                         "reachable_user_y_max_mm": 100, "pen_travel_x_mm": 20,
                         "home_joints_deg": [-120, 0, -90, -90, -30, 90],
                         "user": 0, "tool": 0, "draw_speed_pct": 12,
                         "draw_blend_pct": 100, "travel_speed_pct": 50,
                         "accel_pct": 20},
        }), encoding="utf-8")
        self.control_config.write_text(json.dumps({
            "version": 2, "production_ready": False,
            "selected_mode": "localized_baseline",
            "json_mm_per_rail_mm": -1,
            "baseline": {"initial_json_axis_offset_mm": 0,
                         "speed_mm_s": 50, "refresh_ms": 100,
                         "hold_ms": 250, "max_distance_mm": 300,
                         "settle_ms": 2000},
            "localized_baseline": {"poll_ms": 100,
                                   "localization_timeout_ms": 10000},
            "advanced": {"poll_ms": 100, "station_timeout_ms": 30000,
                         "localization_timeout_ms": 10000},
        }), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def command(self, *extra):
        return [str(self.drawing), "--drawing-config", str(self.config),
                "--control-config", str(self.control_config),
                "--output", str(self.output), "--simulated-reachable-min-mm", "-60",
                "--simulated-reachable-max-mm", "40", *extra]

    def test_cli_has_no_execution_or_device_endpoint_options(self):
        destinations = {action.dest for action in SIM.argument_parser()._actions}
        for forbidden in ("execute", "host", "port", "runtime_config"):
            self.assertNotIn(forbidden, destinations)

    def test_writes_self_contained_two_window_report(self):
        output = io.StringIO()
        with redirect_stdout(output):
            result = SIM.main(self.command())
        self.assertEqual(result, 0)
        report = self.output.read_text(encoding="utf-8")
        self.assertIn("localized-baseline-rehearsal/3", report)
        self.assertIn('"windows":2', report)
        self.assertIn('"actual_true_rail_move_mm"', report)
        self.assertIn('"measured_rail_position_mm"', report)
        self.assertIn('"drawing.control_modes.LocalizedBaselineRelocator"', report)
        self.assertIn('"velocity_calls":7', report)
        self.assertNotIn("__LOCALIZED_BASELINE_SIMULATION_DATA__", report)
        self.assertNotIn("fetch(", report)
        self.assertIn("SIMULATION_ONLY no runtime config", output.getvalue())
        source = (ROOT / "app" / "localized_baseline_sim.py").read_text(encoding="utf-8")
        self.assertNotIn("runtime_core", source)
        self.assertNotIn("maixcam", source.lower())
        self.assertNotIn("chassis", source.lower())

    def test_existing_report_is_preserved_without_force(self):
        self.output.write_text("preserve", encoding="utf-8")
        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            result = SIM.main(self.command())
        self.assertEqual(result, 2)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "preserve")


if __name__ == "__main__":
    unittest.main()
