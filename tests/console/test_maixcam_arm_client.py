import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "protocol"))
sys.path.insert(0, str(ROOT / "src/maixcam/arm"))
sys.path.insert(0, str(ROOT / "src/console"))

from arm_motion_gateway import ArmMotionGateway
from command_service import ArmCommandService
from maixcam_arm_client import MaixCamArmClient, MaixCamArmUnknown
from motion_link import decode_frame, encode_frame


class QueryLoopback:
    def __init__(self):
        self.writes, self.responses = [], []
        self.service = ArmCommandService(ArmMotionGateway(self.writes.append), admission=lambda _message: False)
    def send(self, data):
        reply = self.service.feed_computer(data)
        request = decode_frame(self.writes.pop(0))
        response_type = "PONG" if request["type"] == "PING" else "STATE"
        response_payload = "protocol=2" if response_type == "PONG" else "service_state=ready;motion_enabled=0;active_sequence=0;last_error=none;terminal_position_supported=0;cancel_supported=0"
        reply += self.service.feed_uart(encode_frame("RPA2", response_type, request["sequence"], 0, response_payload))
        self.responses.append(reply)
        return len(data)
    def recv(self, _size): return self.responses.pop(0) if self.responses else b""


class MaixCamArmClientTests(unittest.TestCase):
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
