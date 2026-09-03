"""Deterministic fault/preflight/recovery tests; no vendor or hardware IO."""

import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
for path in ("protocol", "src/robot_arm/runtime"):
    sys.path.insert(0, str(ROOT / path))

from arm_faults import ArmFault, ControllerFaultAccess, fault_record, fault_payload
from arm_motion_service import ArmMotionService, ArmSafetyPolicy, DobotControllerApi
from motion_link import decode_fault, decode_frame, encode_fields, encode_frame


class Rig:
    def __init__(self):
        self.calls = []
        self.pose = [100, 200, 300, 10, 20, 30]
        self.check = 0
        self.after = {"alarm_codes": [26], "stationary": True, "queue_empty": True, "emergency_stop": False}
        self.clear_count = 0
        self.clear_result = 0
        self.persist = False
        self.motion_failure = None

    def get_pose(self, user, tool):
        self.calls.append(("GetPose", user, tool))
        return self.pose

    def check_l(self, point, options):
        self.calls.append(("CheckMovL", point, options.copy()))
        if isinstance(self.check, Exception): raise self.check
        return self.check

    def check_j(self, point, options):
        self.calls.append(("CheckMovJ", point, options.copy()))
        return self.check

    def move(self, *args):
        self.calls.append(("motion", args))
        if self.motion_failure: raise self.motion_failure

    def read(self):
        return dict(self.after, alarm_codes=list(self.after["alarm_codes"]))

    def clear(self):
        self.clear_count += 1
        if not self.persist: self.after["alarm_codes"] = []
        if isinstance(self.clear_result, Exception): raise self.clear_result
        return self.clear_result

    def service(self, supported=False, clock_ms=lambda: 1234):
        access = ControllerFaultAccess(self.read, self.clear) if supported else None
        api = DobotControllerApi(self.check_j, self.move, self.check_l, self.move,
                                 self.move, self.move, self.move, lambda: [1] * 6, self.get_pose, access)
        return ArmMotionService(api, ArmSafetyPolicy(yolo_mode=True), clock_ms)


XYZ = encode_fields((("translation_mm", "1,-2,3"), ("user", 2), ("tool", 3), ("accel_pct", 5), ("speed_pct", 6), ("blend_mm", 0)))
LINEAR = encode_fields((("pose", "1,2,3,4,5,6"), ("user", 2), ("tool", 3), ("accel_pct", 5), ("speed_pct", 6), ("blend_mm", 0)))
JOINT = encode_fields((("joint_deg", "1,2,3,4,5,6"), ("accel_pct", 5), ("speed_pct", 6), ("blend_pct", 0)))


def send(service, kind, payload="", seq=1, emit=None):
    replies, errors = service.feed(encode_frame("RPA2", kind, seq, 1000, payload), emit=emit)
    assert not errors
    return [decode_frame(reply) for reply in replies]


class FaultFoundationTests(unittest.TestCase):
    def test_xyz_preflight_uses_matching_user_tool_and_preserves_orientation(self):
        rig = Rig()
        result = send(rig.service(), "RELLINEAR", XYZ)
        self.assertEqual(result[-1]["type"], "DONE")
        self.assertEqual(rig.calls[0], ("GetPose", 2, 3))
        self.assertEqual(rig.calls[1], ("CheckMovL", {"pose": [101, 198, 303, 10, 20, 30]}, {"user": 2, "tool": 3, "a": 5, "v": 6, "r": 0}))
        self.assertEqual(rig.calls[2][1][0], [1, -2, 3, 0, 0, 0])

    def test_every_nonzero_preflight_result_blocks_motion_and_preserves_numeric_code(self):
        for kind, payload in (("RELLINEAR", XYZ), ("MOVEL", LINEAR), ("MOVEJ", JOINT)):
            for code in (16, 17, 18, 26, 27, 29, -1, 999):
                with self.subTest(kind=kind, code=code):
                    rig = Rig(); rig.check = code
                    reply = send(rig.service(), kind, payload)[-1]
                    fault = decode_fault(reply["payload"])
                    self.assertEqual(reply["type"], "ERROR")
                    self.assertEqual(fault["vendor_code"], str(code))
                    self.assertEqual(fault["sample_time_ms"], "1234")
                    self.assertEqual(fault["category"], "preflight")
                    self.assertEqual(json.loads(bytes.fromhex(fault["raw_hex"])), code)
                    self.assertFalse(any(call[0] == "motion" for call in rig.calls))

    def test_unverified_shapes_never_become_success_or_fabricated_minus_one(self):
        for value in (True, False, None, "0", [], (0, 26), (0, "unknown"), {"code": 0}, 2 ** 100):
            rig = Rig(); rig.check = value
            fault = decode_fault(send(rig.service(), "RELLINEAR", XYZ)[-1]["payload"])
            self.assertEqual(fault["error_code"], "preflight_result_unverified")
            self.assertEqual(fault["vendor_code"], "unknown")
            self.assertFalse(any(call[0] == "motion" for call in rig.calls))

    def test_bad_pose_and_check_exceptions_fail_before_motion(self):
        for pose in ([1, 2], [True] * 6, [float("nan")] * 6, (1, [1] * 6)):
            rig = Rig(); rig.pose = pose
            fault = decode_fault(send(rig.service(), "RELLINEAR", XYZ)[-1]["payload"])
            self.assertEqual(fault["error_code"], "xyz_preflight_pose_unavailable")
            self.assertEqual(len(rig.calls), 1)
        rig = Rig(); rig.check = RuntimeError("check failed")
        fault = decode_fault(send(rig.service(), "RELLINEAR", XYZ)[-1]["payload"])
        self.assertEqual(fault["vendor_api"], "CheckMovL")
        self.assertFalse(any(call[0] == "motion" for call in rig.calls))

    def test_default_capability_gates_do_not_call_undocumented_functions(self):
        rig = Rig(); service = rig.service()
        caps = send(service, "CAPS")[-1]["payload"]
        self.assertIn("xyz_preflight=1", caps)
        self.assertIn("controller_query=0;controller_clear=0;service_recover=0", caps)
        for seq, kind in enumerate(("CLEARERR", "RECOVER"), 2):
            fault = decode_fault(send(service, kind, "confirm=1", seq)[-1]["payload"])
            self.assertTrue(fault["error_code"].endswith("unsupported"))
        self.assertEqual(rig.clear_count, 0)
        self.assertEqual(rig.calls, [])

    def test_clear_and_service_recover_are_separate_and_do_not_replay(self):
        rig = Rig(); service = rig.service(True)
        rig.motion_failure = RuntimeError("native_failed")
        send(service, "MOVEJ", JOINT)
        self.assertEqual(service.service_state, "fault")
        history = list(service.fault_history)
        clear = send(service, "CLEARERR", "confirm=1", 2)
        self.assertEqual(clear[-1]["type"], "DONE")
        self.assertIn("before_raw_hex=5b32365d", clear[-1]["payload"])
        self.assertIn("clear_vendor_code=0", clear[-1]["payload"])
        self.assertEqual(service.service_state, "fault")
        count = len(rig.calls)
        recovery = send(service, "RECOVER", "confirm=1", 3)
        self.assertEqual(recovery[-1]["payload"], "recovery=service_ready;motion_resumed=0")
        self.assertEqual(service.service_state, "ready")
        self.assertEqual(service.fault_history, history)
        self.assertEqual(len(rig.calls), count)
        send(service, "CLEARERR", "confirm=1", 2)
        self.assertEqual(rig.clear_count, 1)

    def test_duplicate_clear_is_cached_not_reexecuted(self):
        rig = Rig(); service = rig.service(True)
        first = send(service, "CLEARERR", "confirm=1")
        self.assertEqual(send(service, "CLEARERR", "confirm=1"), first)
        self.assertEqual(rig.clear_count, 1)

    def test_clear_requires_confirmation_and_verified_stationary_empty_queue_no_estop(self):
        for overrides in ({"stationary": False}, {"queue_empty": False}, {"emergency_stop": True}, {"stationary": 1}):
            rig = Rig(); rig.after.update(overrides)
            result = send(rig.service(True), "CLEARERR", "confirm=1")
            self.assertEqual(result[-1]["type"], "ERROR")
            self.assertEqual(rig.clear_count, 0)
        rig = Rig(); result = send(rig.service(True), "CLEARERR", "confirm=0")
        self.assertIn("recovery_confirmation_required", result[-1]["payload"])
        self.assertEqual(rig.clear_count, 0)

    def test_clear_failure_or_persisting_alarm_never_reports_success(self):
        for value in (True, "0", -1, RuntimeError("unknown")):
            rig = Rig(); rig.clear_result = value
            reply = send(rig.service(True), "CLEARERR", "confirm=1")[-1]
            self.assertEqual(reply["type"], "ERROR")
            self.assertIn("controller_clear_unconfirmed", reply["payload"])
            self.assertEqual(rig.clear_count, 1)
        rig = Rig(); rig.persist = True
        reply = send(rig.service(True), "CLEARERR", "confirm=1")[-1]
        self.assertIn("controller_alarm_persists", reply["payload"])

    def test_clear_requires_valid_post_query_and_freezes_before_evidence(self):
        rig = Rig(); service = rig.service(True)
        state = rig.after
        service.fault_access.read = lambda: state
        def clear():
            state["alarm_codes"].clear()
            return 0
        service.fault_access.clear = clear
        reply = send(service, "CLEARERR", "confirm=1")[-1]
        self.assertIn("before_raw_hex=5b32365d", reply["payload"])
        rig = Rig(); service = rig.service(True)
        def bad_clear():
            rig.after["stationary"] = False
            rig.after["alarm_codes"] = []
            return 0
        service.fault_access.clear = bad_clear
        reply = send(service, "CLEARERR", "confirm=1")[-1]
        self.assertEqual(reply["type"], "ERROR")
        self.assertIn("controller_recovery_unsafe", reply["payload"])

    def test_recover_refuses_active_alarm_and_does_not_clear_it(self):
        rig = Rig(); service = rig.service(True); service.service_state = "fault"
        reply = send(service, "RECOVER", "confirm=1")[-1]
        self.assertIn("controller_alarm_active", reply["payload"])
        self.assertEqual(service.service_state, "fault")
        self.assertEqual(rig.clear_count, 0)

    def test_emit_precedes_vendor_motion_and_duplicate_does_not_move_again(self):
        rig = Rig(); service = rig.service(); emitted = []
        def move(*_):
            self.assertEqual([decode_frame(frame)["type"] for frame in emitted], ["ACK", "RUNNING"])
            rig.calls.append(("motion",))
        service.api.movj = move
        result = send(service, "MOVEJ", JOINT, emit=emitted.append)
        self.assertEqual([decode_frame(frame) for frame in emitted], result)
        emitted.clear()
        send(service, "MOVEJ", JOINT, emit=emitted.append)
        self.assertEqual(sum(call[0] == "motion" for call in rig.calls), 1)

    def test_failed_early_reply_write_never_enters_motion(self):
        rig = Rig(); service = rig.service()
        def fail(_): raise OSError("transport lost")
        with self.assertRaises(OSError): send(service, "MOVEJ", JOINT, emit=fail)
        self.assertFalse(any(call[0] == "motion" for call in rig.calls))

    def test_buffered_clear_expires_while_previous_native_call_blocks(self):
        rig = Rig(); clock = [0]
        service = rig.service(True, clock_ms=lambda: clock[0])
        service.api.movj = lambda *_: clock.__setitem__(0, 2000)
        data = encode_frame("RPA2", "MOVEJ", 1, 1000, JOINT) + encode_frame("RPA2", "CLEARERR", 2, 1000, "confirm=1")
        result, errors = service.feed(data)
        self.assertEqual(errors, [])
        self.assertIn("error_code=expired", decode_frame(result[-1])["payload"])
        self.assertEqual(rig.clear_count, 0)

    def test_ascii_bounded_fault_with_explicit_truncation_and_history_retention(self):
        error = ArmFault("x" * 64, "c" * 64, "a" * 64, -2147483648, "报警;|=\n" * 100)
        record = fault_record(error, lambda: 9223372036854775807, 9223372036854775807)
        frame = encode_frame("RPA2", "ERROR", 2147483647, 0, fault_payload(record))
        self.assertLessEqual(len(frame), 512)
        self.assertEqual(decode_fault(decode_frame(frame)["payload"])["raw_truncated"], "1")
        rig = Rig(); service = rig.service(); rig.check = 26
        send(service, "RELLINEAR", XYZ)
        send(service, "STATUS", seq=2)
        query = send(service, "FAULTS", "scope=service", 3)[-1]
        self.assertEqual(decode_fault(query["payload"])["vendor_code"], "26")


if __name__ == "__main__":
    unittest.main()
