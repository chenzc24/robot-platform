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
        self.config = folder / "drawing.local.json"
        self.output = folder / "rehearsal.html"
        self.drawing.write_text(json.dumps({
            "version": "1.0", "coordinate_space": "normalized",
            "axis": {"origin": "top-left", "x_positive": "right", "y_positive": "down"},
            "canvas": {"width": 1, "height": 1, "source_width": 10,
                       "source_height": 10, "source_aspect_ratio": 1,
                       "target_width_mm": 100, "target_height_mm": 80},
            "strokes": [{"id": "s1", "order": 1,
                         "points": [[0, 0], [0.5, 0.5], [1, 1]], "closed": False}],
        }), encoding="utf-8")
        site = json.loads(
            (ROOT / "config" / "drawing.example.json").read_text(encoding="utf-8")
        )
        site["drawing"]["group_pen_slots"]["default"] = "P1"
        geometry = site["drawing"]["geometry"]
        geometry.update(
            canvas_width_mm=100,
            canvas_height_mm=80,
            canvas_top_left_from_home_mm=[0, -50, 40],
            canvas_u_vector_from_home_mm=[0, 100, 0],
            canvas_v_vector_from_home_mm=[0, 0, -80],
            reachable_home_relative_y_min_mm=-100,
            reachable_home_relative_y_max_mm=100,
        )
        site["relocation"]["selected_mode"] = "localized_baseline"
        self.config.write_text(json.dumps(site), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def command(self, *extra):
        return [str(self.drawing), "--site-config", str(self.config),
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
        self.assertIn('"velocity_calls":13', report)
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
