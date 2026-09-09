"""Unified image/JSON drawing runner gates."""

import importlib.util
import io
import json
import pathlib
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout


ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("run_drawing", ROOT / "app/run_drawing.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class UnifiedRunDrawingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        folder = pathlib.Path(self.temp.name)
        self.drawing = folder / "drawing.json"
        self.site_config = folder / "drawing.local.json"
        self.drawing.write_text(json.dumps({
            "version": "1.0", "coordinate_space": "normalized",
            "axis": {"origin": "top-left", "x_positive": "right", "y_positive": "down"},
            "canvas": {"width": 1, "height": 0.8, "source_width": 10,
                       "source_height": 8, "source_aspect_ratio": 1.25,
                       "target_width_mm": 700, "target_height_mm": 200},
            "strokes": [{"id": "s1", "order": 1,
                         "points": [[0, 0], [1, 0.8]], "closed": False}],
        }), encoding="utf-8")
        site = json.loads(
            (ROOT / "config" / "drawing.example.json").read_text(encoding="utf-8")
        )
        site["relocation"]["selected_mode"] = "baseline"
        site["drawing"]["group_pen_slots"]["default"] = "P1"
        self.site_config.write_text(json.dumps(site), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def command(self, *extra):
        return [str(self.drawing), "--site-config", str(self.site_config), *extra]

    def test_configured_mode_uses_one_no_device_dry_run(self):
        original = RUNNER.load_runtime_config
        RUNNER.load_runtime_config = lambda *_: self.fail("dry-run loaded runtime")
        try:
            output = io.StringIO()
            with redirect_stdout(output):
                result = RUNNER.main(self.command())
            self.assertEqual(result, 0)
            self.assertIn('"mode": "baseline"', output.getvalue())
            self.assertIn("DRY_RUN no device connection or motion", output.getvalue())
        finally:
            RUNNER.load_runtime_config = original

    def test_execute_requires_one_attended_confirmation_before_runtime(self):
        original = RUNNER.load_runtime_config
        RUNNER.load_runtime_config = lambda *_: self.fail("loaded runtime before hash gate")
        try:
            error = io.StringIO()
            with redirect_stderr(error), redirect_stdout(io.StringIO()):
                result = RUNNER.main(self.command("--execute"))
            self.assertEqual(result, 2)
            self.assertIn("execution_admission_required", error.getvalue())
        finally:
            RUNNER.load_runtime_config = original

    def test_execute_uses_the_single_site_production_gate(self):
        error = io.StringIO()
        with redirect_stderr(error), redirect_stdout(io.StringIO()):
            result = RUNNER.main(self.command("--execute", "--attended"))
        self.assertEqual(result, 2)
        self.assertIn("drawing_site_not_production_ready", error.getvalue())


if __name__ == "__main__":
    unittest.main()
