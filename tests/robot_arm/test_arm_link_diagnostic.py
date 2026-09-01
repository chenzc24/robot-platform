"""Tests for the arm-side no-motion LAN1 diagnostic project."""

import importlib.util
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
ARM_PATH = ROOT / "src" / "robot_arm" / "diagnostics" / "arm_link_diagnostic.py"
MAIX_ARM_DIR = ROOT / "src" / "maixcam" / "arm"
sys.path.insert(0, str(MAIX_ARM_DIR))

from link_protocol import decode_frame, encode_frame


spec = importlib.util.spec_from_file_location("arm_diagnostic_target", ARM_PATH)
target = importlib.util.module_from_spec(spec)
spec.loader.exec_module(target)


class ArmLinkDiagnosticTests(unittest.TestCase):
    def test_ping_returns_matching_pong(self):
        responses = target.DiagnosticSession().feed(encode_frame("PING", 91))
        self.assertEqual(len(responses), 1)
        self.assertEqual(
            decode_frame(responses[0].encode("ascii")),
            {"type": "PONG", "sequence": 91, "payload": ""},
        )

    def test_fragmented_and_sticky_input_is_supported(self):
        session = target.DiagnosticSession()
        first = encode_frame("PING", 1)
        second = encode_frame("PING", 2)
        self.assertEqual(session.feed(first[:4]), [])
        responses = session.feed(first[4:] + second)
        self.assertEqual(
            [decode_frame(item.encode("ascii"))["sequence"] for item in responses],
            [1, 2],
        )

    def test_legacy_and_corrupt_input_are_silently_dropped(self):
        session = target.DiagnosticSession()
        self.assertEqual(session.feed(b"Initialize\n"), [])
        frame = bytearray(encode_frame("PING", 1))
        frame[-2] = ord("0") if frame[-2] != ord("0") else ord("1")
        self.assertEqual(session.feed(frame), [])

    def test_valid_non_ping_request_returns_motion_disabled(self):
        request = target.encode_frame("MOVE", 7)
        response = target.DiagnosticSession().feed(request)[0]
        decoded = decode_frame(response.encode("ascii"))
        self.assertEqual(decoded["type"], "ERROR")
        self.assertEqual(decoded["payload"], "motion_disabled")

    def test_fixed_step_executes_once_and_duplicate_is_rejected(self):
        calls = []
        session = target.DiagnosticSession(lambda: calls.append("step"))
        first = session.feed(encode_frame("STEP", 8))[0]
        duplicate = session.feed(encode_frame("STEP", 9))[0]
        self.assertEqual(calls, ["step"])
        self.assertEqual(decode_frame(first.encode("ascii"))["type"], "DONE")
        self.assertEqual(
            decode_frame(duplicate.encode("ascii"))["payload"],
            "motion_already_consumed",
        )

    def test_fixed_step_failure_is_not_retried(self):
        def fail():
            raise RuntimeError("controller error")

        session = target.DiagnosticSession(fail)
        response = session.feed(encode_frame("STEP", 10))[0]
        self.assertEqual(
            decode_frame(response.encode("ascii"))["payload"], "motion_failed"
        )

    def test_formal_project_contains_only_the_fixed_motion(self):
        library = ARM_PATH.read_text(encoding="utf-8")
        standalone = ARM_PATH.with_name("main.py").read_text(encoding="utf-8")
        for token in ("MovL(", "ServoJ(", "EnableRobot(", "DO("):
            self.assertNotIn(token, library)
            self.assertNotIn(token, standalone)
        self.assertNotIn("MovJ(", library)
        self.assertNotRegex(standalone, r"(?<!RelJoint)MovJ\(")
        self.assertNotIn("RelJointMovJ(", library)
        self.assertEqual(standalone.count("RelJointMovJ("), 2)
        self.assertIn('RelJointMovJ([1, 0, 0, 0, 0, 0], motion_options)', standalone)
        self.assertIn('RelJointMovJ([-1, 0, 0, 0, 0, 0], motion_options)', standalone)
        self.assertIn('motion_options = {"a": 5, "v": 5, "cp": 0}', standalone)
        self.assertNotIn("from arm_link_diagnostic import", standalone)
        self.assertIn("TCPCreate(True, \"192.168.5.1\", 5200)", standalone)
        self.assertEqual(
            ARM_PATH.with_name("point.json").read_text(encoding="utf-8").strip(),
            "[]",
        )


if __name__ == "__main__":
    unittest.main()
