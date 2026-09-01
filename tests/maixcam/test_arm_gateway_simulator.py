import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "protocol"))
sys.path.insert(0, str(ROOT / "tools" / "sim"))

from arm_gateway_simulator import ArmGatewaySimulator
from control_envelope import EnvelopeStreamDecoder, encode_message


class ArmGatewaySimulatorTests(unittest.TestCase):
    def test_default_simulator_rejects_motion_before_uart(self):
        simulator = ArmGatewaySimulator()
        message = {"version": 1, "kind": "command", "message_id": "m1", "sequence": 1,
                   "target": "arm", "name": "arm.gripper", "ttl_ms": 1000, "payload": {"width_mm": 10}}
        responses = EnvelopeStreamDecoder().feed(simulator.computer_bytes(encode_message(message)))[0]
        self.assertEqual(responses[-1]["lifecycle"], "REJECTED")
        self.assertEqual(simulator.frames, [])
