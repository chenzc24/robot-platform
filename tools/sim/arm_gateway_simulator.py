"""Deterministic non-hardware simulation for the computer-MaixCam-arm path."""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
for path in (ROOT / "protocol", ROOT / "src" / "maixcam" / "arm"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from arm_motion_gateway import ArmMotionGateway
from command_service import ArmCommandService
from motion_link import decode_frame, encode_frame


class ArmGatewaySimulator:
    """Simulate a default-disabled arm endpoint and explicit UART responses."""
    def __init__(self, permit_motion=False):
        self.frames = []
        self.service = ArmCommandService(ArmMotionGateway(self.frames.append), admission=lambda _message: permit_motion)

    def computer_bytes(self, data):
        return self.service.feed_computer(data)

    def respond_to_latest(self, response_type=None, payload=""):
        request = decode_frame(self.frames[-1])
        if response_type is None:
            response_type = "PONG" if request["type"] == "PING" else "STATE" if request["type"] == "STATUS" else "ACK"
        return self.service.feed_uart(encode_frame("RPA2", response_type, request["sequence"], 0, payload))

    def timeout(self):
        return self.service.poll()
