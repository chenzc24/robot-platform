import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "protocol"))
sys.path.insert(0, str(ROOT / "src/maixcam/arm"))
sys.path.insert(0, str(ROOT / "src/console"))

from arm_motion_gateway import ArmMotionGateway
from command_service import ArmCommandService
from maixcam_arm_client import MaixCamArmClient, MaixCamArmUnknown
from control_envelope import EnvelopeStreamDecoder
from motion_link import decode_frame, encode_frame


class QueryLoopback:
    def __init__(self):
        self.writes, self.responses = [], []
        self.requests = []
        self.service = ArmCommandService(ArmMotionGateway(self.writes.append), admission=lambda _message: False)
    def send(self, data):
        reply = self.service.feed_computer(data)
        request = decode_frame(self.writes.pop(0))
        self.requests.append(request)
        response_type = "PONG" if request["type"] == "PING" else "STATE"
        response_payload = "protocol=2" if response_type == "PONG" else "service_state=ready;motion_enabled=0;control_mode=production;active_sequence=0;last_error=none;terminal_position_supported=0;cancel_supported=0;feedback_valid=1;feedback_error=none;joint_deg=1,2,3,4,5,6;pose=101,202,303,1.5,2.5,3.5;pose_user=0;pose_tool=0;sample_id=1;sample_time_ms=1234"
        reply += self.service.feed_uart(encode_frame("RPA2", response_type, request["sequence"], 0, response_payload))
        self.responses.append(reply)
        return len(data)
    def recv(self, _size): return self.responses.pop(0) if self.responses else b""


class MaixCamArmClientTests(unittest.TestCase):
    def test_query_defaults_reach_gateway_with_five_second_ttl(self):
        connection = QueryLoopback()
        client = MaixCamArmClient(connection)
        client.ping()
        client.status()
        self.assertEqual([r["ttl_ms"] for r in connection.requests], [5000, 5000])

    def test_response_budget_is_independent_of_connect_timeout_and_restored(self):
        connection = QueryLoopback()
        timeouts = []
        connection.gettimeout = lambda: 3.0
        connection.settimeout = timeouts.append
        with mock.patch("maixcam_arm_client.time.monotonic", return_value=10):
            MaixCamArmClient(connection).status()
        self.assertEqual(timeouts, [6.0, 6.0, 3.0])

    def test_motion_response_budget_matches_motion_ttl_without_retry(self):
        class LostConnection:
            sends = 0
            timeouts = []
            def gettimeout(self): return 3.0
            def settimeout(self, value): self.timeouts.append(value)
            def send(self, data): self.sends += 1; return len(data)
            def recv(self, _size): raise TimeoutError("no response")
        connection = LostConnection()
        with mock.patch("maixcam_arm_client.time.monotonic", return_value=10):
            with self.assertRaises(MaixCamArmUnknown):
                MaixCamArmClient(connection).jog_joint((2, 0, 0, 0, 0, 0))
        self.assertEqual(connection.timeouts, [61.0, 61.0, 3.0])
        self.assertEqual(connection.sends, 1)

    def test_send_time_counts_toward_absolute_response_deadline(self):
        connection = QueryLoopback()
        connection.service.gateway.clock_ms = lambda: 0
        with mock.patch("maixcam_arm_client.time.monotonic", side_effect=[10, 10, 17]):
            with self.assertRaisesRegex(TimeoutError, "arm_response_deadline"):
                MaixCamArmClient(connection).status()
        self.assertEqual(len(connection.requests), 1)

    def test_ping_receives_full_lifecycle_over_one_connection(self):
        states = MaixCamArmClient(QueryLoopback()).ping()
        self.assertEqual([item["lifecycle"] for item in states], ["RECEIVED", "ACCEPTED", "DONE"])

    def test_lost_motion_response_is_unknown_without_retry(self):
        class LostConnection:
            def __init__(self): self.sends = 0
            def send(self, data): self.sends += 1; return len(data)
            def recv(self, _size): raise TimeoutError("timeout")
        connection = LostConnection()
        with self.assertRaises(MaixCamArmUnknown):
            MaixCamArmClient(connection).gripper(10)
        self.assertEqual(connection.sends, 1)

    def test_joint_jog_is_state_changing_and_not_retried(self):
        class JogConnection:
            def __init__(self): self.sent = []
            def send(self, data): self.sent.append(data); return len(data)
            def recv(self, _size): raise TimeoutError("timeout")
        connection = JogConnection()
        with self.assertRaises(MaixCamArmUnknown):
            MaixCamArmClient(connection).jog_joint((2, 0, 0, 0, 0, 0))
        self.assertEqual(len(connection.sent), 1)

    def test_xyz_jog_emits_explicit_blend_percentage(self):
        class CaptureConnection:
            def __init__(self): self.sent = []
            def send(self, data): self.sent.append(data); return len(data)
            def recv(self, _size): raise TimeoutError("stop after capture")
        connection = CaptureConnection()
        with self.assertRaises(MaixCamArmUnknown):
            MaixCamArmClient(connection).jog_xyz(
                (0, 1, 2), accel_pct=20, speed_pct=12, blend_pct=100
            )
        messages, errors = EnvelopeStreamDecoder().feed(b"".join(connection.sent))
        self.assertEqual(errors, [])
        self.assertEqual(messages[0]["payload"]["blend_pct"], 100)
