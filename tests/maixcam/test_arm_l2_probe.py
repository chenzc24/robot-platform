"""One-shot execution tests for the MaixCam arm link probe."""

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


spec = importlib.util.spec_from_file_location("arm_l2_probe", ARM_DIR / "l2_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class LoopbackTransport:
    def __init__(self, respond=True):
        self.respond = respond
        self.response = b""
        self.closed = False

    def write(self, data):
        request = decode_frame(data)
        if self.respond:
            self.response = encode_frame("PONG", request["sequence"])
        return len(data)

    def read(self):
        response = self.response
        self.response = b""
        return response

    def close(self):
        self.closed = True


class ArmL2ProbeTests(unittest.TestCase):
    def test_loopback_probe_reports_ready_and_no_motion(self):
        transport = LoopbackTransport()
        result = probe.run_probe(transport, timeout_seconds=1.0, sleep=lambda _: None)
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "ready")
        self.assertFalse(result["motion_enabled"])

    def test_cli_closes_transport_and_emits_json(self):
        transport = LoopbackTransport()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = probe.main(
                [], transport_factory=lambda _device, _baud: transport
            )
        result = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(result["ok"])
        self.assertTrue(transport.closed)

    def test_open_failure_is_fail_closed(self):
        def fail_open(_device, _baud):
            raise OSError("busy")

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = probe.main([], transport_factory=fail_open)
        result = json.loads(output.getvalue())
        self.assertEqual(code, 1)
        self.assertFalse(result["motion_enabled"])
        self.assertEqual(result["state"], "fault")


if __name__ == "__main__":
    unittest.main()
