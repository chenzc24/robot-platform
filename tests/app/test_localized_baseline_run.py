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
    def test_connection_timeout_has_device_specific_error(self):
        def timed_out(_config):
            raise TimeoutError("timed out")

        with self.assertRaisesRegex(RUNNER.DrawingError, "chassis_connect_timeout"):
            RUNNER._connect_device(timed_out, object(), "chassis")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        folder = pathlib.Path(self.temp.name)
        self.drawing = folder / "drawing.json"
        self.site_config = folder / "drawing.local.json"
        self.drawing.write_text(json.dumps({
            "version": "1.0", "coordinate_space": "normalized",
            "axis": {"origin": "top-left", "x_positive": "right", "y_positive": "down"},
            "canvas": {"width": 1, "height": 1, "source_width": 10,
                       "source_height": 10, "source_aspect_ratio": 1,
                       "target_width_mm": 700, "target_height_mm": 200},
            "strokes": [{"id": "s1", "order": 1,
                         "points": [[0, 0], [1, 1]], "closed": False}],
        }), encoding="utf-8")
        site = json.loads(
            (ROOT / "config" / "drawing.example.json").read_text(encoding="utf-8")
        )
        site["relocation"]["selected_mode"] = "localized_baseline"
        site["drawing"]["group_pen_slots"]["default"] = "P1"
        self.site_config.write_text(json.dumps(site), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def command(self, *extra):
        return [str(self.drawing), "--site-config", str(self.site_config), *extra]

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

    def test_execute_requires_one_attended_confirmation_before_runtime_access(self):
        error = io.StringIO()
        with redirect_stderr(error), redirect_stdout(io.StringIO()):
            result = RUNNER.main(self.command("--execute"))
        self.assertEqual(result, 2)
        self.assertIn("execution_admission_required", error.getvalue())


if __name__ == "__main__":
    unittest.main()
