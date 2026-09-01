import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "protocol"))
sys.path.insert(0, str(ROOT / "src/robot_arm/runtime"))

from arm_motion_service import ArmMotionService, ArmSafetyPolicy, DobotControllerApi
from motion_link import decode_frame, encode_fields, encode_frame


class FakeApi:
    def __init__(self): self.calls = []
    def check_j(self, *_): return 0
    def move_j(self, point, options): self.calls.append(("movj", point, options))
    def check_l(self, *_): return 0
    def move_l(self, point, options): self.calls.append(("movl", point, options))
    def gripper(self, width): self.calls.append(("gripper", width))


class ArmRuntimeTests(unittest.TestCase):
    def service(self, enabled=False):
        raw = FakeApi()
        policy = ArmSafetyPolicy(enabled, (-10,) * 6 if enabled else None, (10,) * 6 if enabled else None,
                                 (-10,) * 6 if enabled else None, (10,) * 6 if enabled else None)
        api = DobotControllerApi(raw.check_j, raw.move_j, raw.check_l, raw.move_l, raw.gripper)
        return ArmMotionService(api, policy), raw

    def test_default_policy_answers_status_and_rejects_move_without_api_call(self):
        service, raw = self.service()
        state, _ = service.feed(encode_frame("RPA2", "STATUS", 1, 1000))
        self.assertIn("motion_enabled=0", decode_frame(state[0])["payload"])
        payload = encode_fields((("joint_deg", "0,0,0,0,0,0"), ("accel_pct", 5), ("speed_pct", 5), ("blend_pct", 0)))
        replies, _ = service.feed(encode_frame("RPA2", "MOVEJ", 2, 1000, payload))
        self.assertEqual(decode_frame(replies[-1])["type"], "ERROR")
        self.assertEqual(raw.calls, [])

    def test_enabled_policy_checks_then_marks_api_return_as_unknown_terminal_position(self):
        service, raw = self.service(True)
        payload = encode_fields((("joint_deg", "1,1,1,1,1,1"), ("accel_pct", 5), ("speed_pct", 5), ("blend_pct", 0)))
        replies, _ = service.feed(encode_frame("RPA2", "MOVEJ", 1, 1000, payload))
        self.assertEqual([decode_frame(reply)["type"] for reply in replies], ["ACK", "RUNNING", "DONE"])
        self.assertIn("terminal_position=unknown", decode_frame(replies[-1])["payload"])
        self.assertEqual(raw.calls[0][0], "movj")
