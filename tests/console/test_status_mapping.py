import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "console"))

from status_mapping import StatusMappingError, parse_arm_status


def response(downstream):
    return [{
        "version": 1,
        "kind": "lifecycle",
        "message_id": "reply-1",
        "sequence": 1,
        "target": "arm",
        "name": "arm.status",
        "ttl_ms": 0,
        "payload": {
            "downstream_sequence": 1,
            "terminal_position": None,
            "downstream_payload": downstream,
        },
        "correlation_id": "console-1",
        "lifecycle": "DONE",
    }]


BASE = "service_state=ready;motion_enabled=1;control_mode=yolo;active_sequence=0;last_error=none;terminal_position_supported=0;cancel_supported=0"


class ArmStatusMappingTests(unittest.TestCase):
    def test_valid_feedback_is_parsed_as_finite_measured_vectors(self):
        downstream = BASE + ";feedback_valid=1;feedback_error=none;joint_deg=1,2,3,4,5,6;pose=101,202,303,1.5,2.5,3.5;pose_user=0;pose_tool=0;sample_id=7;sample_time_ms=1234"
        status = parse_arm_status(response(downstream))
        self.assertTrue(status.feedback_valid)
        self.assertEqual(status.joint_deg, (1.0, 2.0, 3.0, 4.0, 5.0, 6.0))
        self.assertEqual(status.pose, (101.0, 202.0, 303.0, 1.5, 2.5, 3.5))

    def test_malformed_or_contradictory_feedback_is_rejected(self):
        malformed = BASE + ";feedback_valid=1;feedback_error=none;joint_deg=1,2;pose=1,2,3,4,5,6;pose_user=0;pose_tool=0;sample_id=7;sample_time_ms=1234"
        with self.assertRaisesRegex(StatusMappingError, "invalid_arm_status_payload"):
            parse_arm_status(response(malformed))
        contradictory = BASE + ";feedback_valid=0;feedback_error=none;joint_deg=unavailable;pose=unavailable;pose_user=0;pose_tool=0;sample_id=7;sample_time_ms=1234"
        with self.assertRaisesRegex(StatusMappingError, "invalid_arm_status_payload"):
            parse_arm_status(response(contradictory))

    def test_explicit_invalid_feedback_remains_a_valid_service_status(self):
        downstream = BASE + ";feedback_valid=0;feedback_error=feedback_read_failed;joint_deg=unavailable;pose=unavailable;pose_user=0;pose_tool=0;sample_id=8;sample_time_ms=1300"
        status = parse_arm_status(response(downstream))
        self.assertFalse(status.feedback_valid)
        self.assertIsNone(status.joint_deg)
        self.assertEqual(status.feedback_error, "feedback_read_failed")


if __name__ == "__main__":
    unittest.main()
