"""Tests for the side-effect-free MaixCam development probe."""

import importlib.util
import io
import json
import pathlib
import unittest
from contextlib import redirect_stdout


PROBE_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "src"
    / "maixcam"
    / "app"
    / "probe.py"
)


def load_probe_module():
    spec = importlib.util.spec_from_file_location("maixcam_probe", PROBE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProbeTests(unittest.TestCase):
    def test_snapshot_has_stable_identity_fields(self):
        snapshot = load_probe_module().collect_snapshot()
        self.assertEqual(snapshot["probe"], "robot-platform-maixcam")
        self.assertEqual(snapshot["schema_version"], 1)
        self.assertTrue(snapshot["hostname"])
        self.assertTrue(snapshot["machine"])
        self.assertTrue(snapshot["python"])

    def test_main_emits_one_json_object(self):
        module = load_probe_module()
        output = io.StringIO()
        with redirect_stdout(output):
            module.main()
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["probe"], "robot-platform-maixcam")


if __name__ == "__main__":
    unittest.main()
