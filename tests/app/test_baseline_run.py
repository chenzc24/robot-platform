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
                       "source_aspect_ratio": 1, "target_width_mm": 700, "target_height_mm": 200},
            "strokes": [{"id": "s1", "order": 1, "points": [[0.4, 0.4], [0.6, 0.6]], "closed": False}],
        }), encoding="utf-8")
        site = json.loads(
            (ROOT / "config" / "drawing.example.json").read_text(encoding="utf-8")
        )
        site["drawing"]["group_pen_slots"]["default"] = "P1"
        self.config.write_text(json.dumps(site), encoding="utf-8")

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

    def test_execute_requires_one_attended_confirmation(self):
        errors = io.StringIO()
        with redirect_stderr(errors), redirect_stdout(io.StringIO()):
            result = BASELINE_RUN.main([
                str(self.drawing), "--config", str(self.config), "--execute",
            ])
        self.assertEqual(result, 2)
        self.assertIn("execution_admission_required", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
