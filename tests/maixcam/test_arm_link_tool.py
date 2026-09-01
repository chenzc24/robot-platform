"""Safety and output tests for the MaixCam arm-link SSH wrapper."""

import contextlib
import importlib.util
import io
import json
import pathlib
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools" / "maixcam" / "arm_link_l2.py"
spec = importlib.util.spec_from_file_location("arm_link_tool", TOOL_PATH)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def completed(returncode=0, stdout="", stderr=""):
    return types.SimpleNamespace(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class ArmLinkToolTests(unittest.TestCase):
    def test_status_parses_unique_numeric_owner_pids(self):
        result = tool.uart_owner_result(lambda _command: completed(stdout="646 646\n"))
        self.assertTrue(result["ok"])
        self.assertEqual(result["owner_pids"], [646])
        self.assertFalse(result["uart_available"])

    def test_probe_requires_exact_confirmation_before_ssh(self):
        calls = []
        result = tool.probe_result(lambda command: calls.append(command), "yes")
        self.assertEqual(result["error_code"], "safety_confirmation_required")
        self.assertEqual(calls, [])

    def test_probe_accepts_only_valid_json_success(self):
        result = tool.probe_result(
            lambda _command: completed(
                stdout='{"ok": true, "state": "ready"}\n'
            ),
            "ARM_DISABLED",
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["remote_return_code"], 0)

    def test_probe_propagates_guard_failure(self):
        result = tool.probe_result(
            lambda _command: completed(
                returncode=1,
                stdout='{"ok": false, "error_code": "uart_owner_unverified"}\n',
            ),
            "ARM_DISABLED",
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "uart_owner_unverified")

    def test_cli_emits_one_json_object(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = tool.main(
                ["status"], runner=lambda _command: completed(stdout="646\n")
            )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["owner_pids"], [646])


if __name__ == "__main__":
    unittest.main()
