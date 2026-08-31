"""Contract tests shared by ESP32 and MaixCam runtime status emitters."""

import importlib.util
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "protocol" / "runtime-status.schema.json"
IMPLEMENTATIONS = (
    ROOT / "src" / "esp32" / "app" / "esp_runtime_status.py",
    ROOT / "src" / "maixcam" / "video" / "maix_runtime_status.py",
)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_contract(test_case, schema, payload):
    test_case.assertEqual(set(payload), set(schema["required"]))
    test_case.assertEqual(payload["schema_version"], 1)
    test_case.assertIn(payload["state"], schema["properties"]["state"]["enum"])
    test_case.assertIsInstance(payload["event"], str)
    test_case.assertIsInstance(payload["device"], str)
    test_case.assertIsInstance(payload["subsystem"], str)
    test_case.assertIsInstance(payload["sequence"], int)
    test_case.assertGreaterEqual(payload["sequence"], 0)
    test_case.assertIsInstance(payload["uptime_ms"], int)
    test_case.assertGreaterEqual(payload["uptime_ms"], 0)
    test_case.assertTrue(
        payload["error_code"] is None or isinstance(payload["error_code"], str)
    )
    test_case.assertIsInstance(payload["detail"], dict)


class RuntimeStatusContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def test_schema_requires_only_stable_runtime_fields(self):
        self.assertFalse(self.schema["additionalProperties"])
        self.assertEqual(self.schema["properties"]["schema_version"]["const"], 1)
        self.assertIn("safe_idle", self.schema["properties"]["state"]["enum"])
        self.assertIn("fault", self.schema["properties"]["state"]["enum"])

    def test_both_device_implementations_follow_the_contract(self):
        for index, path in enumerate(IMPLEMENTATIONS):
            with self.subTest(path=path):
                output = []
                module = load_module("runtime_status_%d" % index, path)
                status = module.RuntimeStatus(
                    "test-device",
                    "test-subsystem",
                    clock_ms=lambda: 1_000,
                    output=output.append,
                )
                payload = status.transition(
                    "ready",
                    event="service_ready",
                    detail={"healthy": True},
                )
                assert_contract(self, self.schema, payload)
                self.assertEqual(json.loads(output[0]), payload)

    def test_invalid_state_and_detail_are_rejected(self):
        for index, path in enumerate(IMPLEMENTATIONS):
            with self.subTest(path=path):
                module = load_module("invalid_runtime_status_%d" % index, path)
                status = module.RuntimeStatus("test", "test", output=lambda _line: None)
                with self.assertRaises(ValueError):
                    status.transition("unknown")
                with self.assertRaises(ValueError):
                    status.transition("ready", detail="not-an-object")

    def test_schema_identifier_patterns_are_enforced_by_emitters(self):
        for index, path in enumerate(IMPLEMENTATIONS):
            with self.subTest(path=path):
                module = load_module("token_runtime_status_%d" % index, path)
                with self.assertRaises(ValueError):
                    module.RuntimeStatus("Test Device", "test")
                status = module.RuntimeStatus("test-device", "test_subsystem")
                with self.assertRaises(ValueError):
                    status.snapshot("Bad Event")
                with self.assertRaises(ValueError):
                    status.transition("fault", error_code="BAD-CODE")


if __name__ == "__main__":
    unittest.main()
