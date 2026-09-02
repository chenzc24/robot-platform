import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "protocol"))
sys.path.insert(0, str(ROOT / "src/maixcam/arm"))

from arm_motion_gateway import ArmMotionGateway
from command_service import ArmCommandService
from control_envelope import EnvelopeStreamDecoder, encode_message
from motion_link import encode_frame


def command(name, payload=None, sequence=1):
    return {"version": 1, "kind": "command", "message_id": "console-%d" % sequence, "sequence": sequence,
            "target": "arm", "name": name, "ttl_ms": 1000, "payload": payload or {}}


class ArmCommandServiceTests(unittest.TestCase):
    def setUp(self):
        self.writes = []
        self.gateway = ArmMotionGateway(self.writes.append)
        self.service = ArmCommandService(self.gateway, admission=lambda _message: False)

    def messages(self, data): return EnvelopeStreamDecoder().feed(data)[0]

    def test_ping_maps_to_rpa2_and_returns_done_only_after_pong(self):
        initial = self.messages(self.service.feed_computer(encode_message(command("arm.ping"))))
        self.assertEqual([item["lifecycle"] for item in initial], ["RECEIVED", "ACCEPTED"])
        self.assertEqual(len(self.writes), 1)
        done = self.messages(self.service.feed_uart(encode_frame("RPA2", "PONG", 1, 0, "protocol=2")))
        self.assertEqual(done[-1]["lifecycle"], "DONE")
        self.assertEqual(done[-1]["payload"]["terminal_position"], "unknown")

    def test_motion_is_rejected_by_default_without_uart_write(self):
        result = self.messages(self.service.feed_computer(encode_message(command("arm.gripper", {"width_mm": 10}))))
        self.assertEqual(result[-1]["lifecycle"], "REJECTED")
        self.assertEqual(result[-1]["payload"]["error_code"], "admission_rejected")
        self.assertEqual(self.writes, [])

    def test_motion_timeout_is_unknown_and_not_retried(self):
        clock = [0]
        gateway = ArmMotionGateway(lambda frame: len(frame), clock_ms=lambda: clock[0])
        service = ArmCommandService(gateway, admission=lambda _message: True)
        service.feed_computer(encode_message(command("arm.gripper", {"width_mm": 10})))
        clock[0] = 1001
        outcome = self.messages(service.poll())[-1]
        self.assertEqual(outcome["lifecycle"], "UNKNOWN")

    def test_stale_safe_reply_does_not_fault_or_block_newer_request(self):
        clock, writes = [0], []
        gateway = ArmMotionGateway(writes.append, clock_ms=lambda: clock[0])
        service = ArmCommandService(gateway, admission=lambda _message: False)

        service.feed_computer(encode_message(command("arm.ping", sequence=1)))
        clock[0] = 1001
        self.assertEqual(self.messages(service.poll())[-1]["lifecycle"], "FAULT")

        service.feed_computer(encode_message(command("arm.status", sequence=2)))
        self.assertEqual(len(writes), 2)
        stale = self.messages(service.feed_uart(encode_frame("RPA2", "PONG", 1, 0, "protocol=2")))
        self.assertEqual(stale, [])
        done = self.messages(service.feed_uart(encode_frame("RPA2", "STATE", 2, 0, "service_state=ready")))
        self.assertEqual(done[-1]["lifecycle"], "DONE")
