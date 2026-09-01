"""One-shot execution tests for the bounded MaixCam arm motion probe."""

import contextlib
import importlib.util
import io
import json
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
ARM_DIR = ROOT / "src" / "maixcam" / "arm"
sys.path.insert(0, str(ARM_DIR))

from link_protocol import decode_frame, encode_frame


spec = importlib.util.spec_from_file_location("arm_l3_probe", ARM_DIR / "l3_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class LoopbackTransport:
    def __init__(self):
        self.response = b""
        self.closed = False
        self.requests = []

    def write(self, data):
        request = decode_frame(data)
        self.requests.append(request)
        self.response = encode_frame("DONE", request["sequence"])
        return len(data)

    def read(self):
        response = self.response
        self.response = b""
        return response

    def close(self):
        self.closed = True


class ArmL3ProbeTests(unittest.TestCase):
    def test_loopback_sends_exactly_one_parameterless_step(self):
        transport = LoopbackTransport()
        result = probe.run_probe(transport, sleep=lambda _: None)
        self.assertTrue(result["ok"])
        self.assertEqual(
            transport.requests,
            [{"type": "STEP", "sequence": 1, "payload": ""}],
        )

    def test_cli_rejects_wrong_confirmation_before_open(self):
        calls = []
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = probe.main(
                ["--confirmation", "yes"],
                transport_factory=lambda *_args: calls.append("opened"),
            )
        self.assertEqual(code, 2)
        self.assertEqual(calls, [])
        self.assertEqual(
            json.loads(output.getvalue())["error_code"],
            "safety_confirmation_required",
        )

    def test_cli_closes_transport_after_success(self):
        transport = LoopbackTransport()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = probe.main(
                ["--confirmation", probe.CONFIRMATION],
                transport_factory=lambda *_args: transport,
            )
        self.assertEqual(code, 0)
        self.assertTrue(transport.closed)

    def test_guard_requires_confirmation_before_touching_launcher(self):
        guard = (ARM_DIR / "run_guarded_l3.sh").read_text(encoding="utf-8")
        confirmation_check = guard.index('if [ "${1:-}" != "$CONFIRMATION" ]')
        launcher_stop = guard.index('kill -STOP "$supervisor_pid"')
        probe_run = guard.index('python3 "$PROBE"')
        self.assertLess(confirmation_check, launcher_stop)
        self.assertLess(launcher_stop, probe_run)
        self.assertNotIn("while true", guard.lower())


if __name__ == "__main__":
    unittest.main()
