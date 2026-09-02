import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "protocol"))
sys.path.insert(0, str(ROOT / "src/robot_arm/runtime"))

from arm_motion_service import ArmMotionService, ArmSafetyPolicy, DobotControllerApi
from motion_link import decode_fields, decode_frame, encode_fields, encode_frame


class FakeApi:
    def __init__(self):
        self.calls = []
        self.motion_return = "nonempty_controller_return"
        self.angle_result = [1, 2, 3, 4, 5, 6]
        self.pose_result = [100, 200, 300, 10, 20, 30]

    def check_j(self, *_): return 0
    def move_j(self, point, options):
        self.calls.append(("movj", point, options)); return self.motion_return
    def check_l(self, *_): return 0
    def move_l(self, point, options):
        self.calls.append(("movl", point, options)); return self.motion_return
    def gripper(self, width):
        self.calls.append(("gripper", width)); return self.motion_return
    def relative_joint(self, joints, options):
        self.calls.append(("relative_joint", joints, options)); return self.motion_return
    def relative_linear_user(self, pose, options):
        self.calls.append(("relative_linear_user", pose, options)); return self.motion_return
    def get_angle(self): return self.angle_result
    def get_pose(self, _user, _tool): return self.pose_result


class ArmRuntimeTests(unittest.TestCase):
    def service(self, enabled=False, yolo=False, clock_ms=None):
        raw = FakeApi()
        policy = ArmSafetyPolicy(
            enabled,
            (-10,) * 6 if enabled else None, (10,) * 6 if enabled else None,
            (-10,) * 6 if enabled else None, (10,) * 6 if enabled else None,
            yolo_mode=yolo,
        )
        api = DobotControllerApi(
            raw.check_j, raw.move_j, raw.check_l, raw.move_l, raw.gripper,
            raw.relative_joint, raw.relative_linear_user, raw.get_angle, raw.get_pose,
        )
        return ArmMotionService(api, policy, clock_ms=clock_ms), raw

    def test_status_contains_normalized_measured_feedback(self):
        service, raw = self.service(clock_ms=lambda: 1234)
        raw.angle_result = (0, {"joint": [1, 2, 3, 4, 5, 6]})
        raw.pose_result = {"x": 101, "y": 202, "z": 303, "rx": 1.5, "ry": 2.5, "rz": 3.5}
        replies, _ = service.feed(encode_frame("RPA2", "STATUS", 1, 1000))
        values = decode_fields(decode_frame(replies[0])["payload"], (
            "service_state", "motion_enabled", "control_mode", "active_sequence", "last_error",
            "terminal_position_supported", "cancel_supported", "feedback_valid", "feedback_error",
            "joint_deg", "pose", "pose_user", "pose_tool", "sample_id", "sample_time_ms",
        ))
        self.assertEqual(values["feedback_valid"], "1")
        self.assertEqual(values["feedback_error"], "none")
        self.assertEqual(values["joint_deg"], "1,2,3,4,5,6")
        self.assertEqual(values["pose"], "101,202,303,1.5,2.5,3.5")
        self.assertEqual(values["sample_id"], "1")
        self.assertEqual(values["sample_time_ms"], "1234")
        self.assertEqual(values["terminal_position_supported"], "0")

    def test_feedback_failure_is_reported_without_faulting_motion_service(self):
        service, raw = self.service(yolo=True, clock_ms=lambda: 55)
        raw.angle_result = [1, 2]
        replies, _ = service.feed(encode_frame("RPA2", "STATUS", 1, 1000))
        payload = decode_frame(replies[0])["payload"]
        self.assertIn("feedback_valid=0", payload)
        self.assertIn("feedback_error=invalid_joint_feedback", payload)
        self.assertIn("joint_deg=unavailable;pose=unavailable", payload)
        request = encode_fields((("joint_delta_deg", "2,0,0,0,0,0"), ("accel_pct", 5), ("speed_pct", 5), ("blend_pct", 0)))
        motion, _ = service.feed(encode_frame("RPA2", "RELJOINT", 2, 1000, request))
        self.assertEqual(decode_frame(motion[-1])["type"], "DONE")

    def test_default_policy_answers_status_and_rejects_motion(self):
        service, raw = self.service()
        state, _ = service.feed(encode_frame("RPA2", "STATUS", 1, 1000))
        payload = decode_frame(state[0])["payload"]
        self.assertIn("motion_enabled=0", payload)
        self.assertIn("control_mode=production", payload)
        request = encode_fields((("joint_delta_deg", "2,0,0,0,0,0"), ("accel_pct", 5), ("speed_pct", 5), ("blend_pct", 0)))
        replies, _ = service.feed(encode_frame("RPA2", "RELJOINT", 2, 1000, request))
        self.assertIn("error_code=yolo_mode_required", decode_frame(replies[-1])["payload"])
        self.assertEqual(raw.calls, [])

    def test_yolo_relative_joint_is_repeatable_and_ignores_nonempty_api_return(self):
        service, raw = self.service(yolo=True)
        status, _ = service.feed(encode_frame("RPA2", "STATUS", 1, 1000))
        self.assertIn("control_mode=yolo", decode_frame(status[0])["payload"])
        request = encode_fields((("joint_delta_deg", "2,0,0,0,0,0"), ("accel_pct", 5), ("speed_pct", 5), ("blend_pct", 0)))
        first, _ = service.feed(encode_frame("RPA2", "RELJOINT", 2, 60000, request))
        second, _ = service.feed(encode_frame("RPA2", "RELJOINT", 3, 60000, request))
        self.assertEqual([decode_frame(item)["type"] for item in first], ["ACK", "RUNNING", "DONE"])
        self.assertEqual([decode_frame(item)["type"] for item in second], ["ACK", "RUNNING", "DONE"])
        self.assertEqual(raw.calls, [
            ("relative_joint", [2.0, 0.0, 0.0, 0.0, 0.0, 0.0], {"a": 5, "v": 5, "cp": 0}),
            ("relative_joint", [2.0, 0.0, 0.0, 0.0, 0.0, 0.0], {"a": 5, "v": 5, "cp": 0}),
        ])

    def test_yolo_xyz_maps_to_relmovluser_with_zero_rotation(self):
        service, raw = self.service(yolo=True)
        request = encode_fields((("translation_mm", "0,-5,0"), ("user", 0), ("tool", 0), ("accel_pct", 6), ("speed_pct", 7), ("blend_mm", 0)))
        replies, _ = service.feed(encode_frame("RPA2", "RELLINEAR", 1, 60000, request))
        self.assertEqual(decode_frame(replies[-1])["type"], "DONE")
        self.assertEqual(raw.calls, [
            ("relative_linear_user", [0.0, -5.0, 0.0, 0, 0, 0], {"user": 0, "tool": 0, "a": 6, "v": 7, "r": 0}),
        ])

    def test_invalid_relative_vector_is_rejected_before_controller_call(self):
        service, raw = self.service(yolo=True)
        request = encode_fields((("joint_delta_deg", "2,0"), ("accel_pct", 5), ("speed_pct", 5), ("blend_pct", 0)))
        replies, _ = service.feed(encode_frame("RPA2", "RELJOINT", 1, 1000, request))
        self.assertIn("error_code=invalid_joint_delta", decode_frame(replies[-1])["payload"])
        self.assertEqual(raw.calls, [])

    def test_yolo_also_allows_absolute_programmatic_motion(self):
        service, raw = self.service(yolo=True)
        payload = encode_fields((("joint_deg", "1,1,1,1,1,1"), ("accel_pct", 80), ("speed_pct", 90), ("blend_pct", 0)))
        replies, _ = service.feed(encode_frame("RPA2", "MOVEJ", 1, 1000, payload))
        self.assertEqual(decode_frame(replies[-1])["type"], "DONE")
        self.assertEqual(raw.calls[0][0], "movj")

    def test_specific_controller_exception_reaches_protocol_log(self):
        service, _ = self.service(yolo=True)
        def fail(*_): raise RuntimeError("controller_movj_failed")
        service.api.movj = fail
        payload = encode_fields((("joint_deg", "1,1,1,1,1,1"), ("accel_pct", 5), ("speed_pct", 5), ("blend_pct", 0)))
        replies, _ = service.feed(encode_frame("RPA2", "MOVEJ", 1, 1000, payload))
        self.assertIn("error_code=controller_movj_failed", decode_frame(replies[-1])["payload"])


if __name__ == "__main__":
    unittest.main()
