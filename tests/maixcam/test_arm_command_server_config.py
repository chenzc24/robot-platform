import importlib
import pathlib
import sys
import types
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
ARM_DIR = ROOT / "src" / "maixcam" / "arm"
PROTOCOL_DIR = ROOT / "protocol"
sys.path.insert(0, str(ARM_DIR))
sys.path.insert(0, str(PROTOCOL_DIR))

from control_envelope import encode_message
from motion_link import decode_frame, encode_frame


class ArmCommandServerConfigTests(unittest.TestCase):
    def test_default_deny_configuration_template_is_importable_by_the_server(self):
        sys.modules.pop("arm_command_server", None)
        server = importlib.import_module("arm_command_server")
        # A local deployment override must not become the default-deny fixture.
        with mock.patch.dict(sys.modules, {"arm_service_config": None}):
            config = server._settings()
        self.assertEqual(config.LISTEN_ADDRESS, "0.0.0.0")
        self.assertEqual(config.LISTEN_PORT, 8780)
        self.assertEqual(config.UART_DEVICE, "/dev/ttyS0")
        self.assertEqual(config.UART_BAUD, 115200)
        self.assertFalse(config.YOLO_MODE)

    def test_explicit_local_override_takes_precedence_over_the_template(self):
        server = importlib.import_module("arm_command_server")
        local = types.ModuleType("arm_service_config")
        local.YOLO_MODE = True
        with mock.patch.dict(sys.modules, {"arm_service_config": local}):
            self.assertIs(server._settings(), local)

    def test_yolo_mode_admits_motion_without_named_allowlist(self):
        sys.modules.pop("arm_command_server", None)
        server = importlib.import_module("arm_command_server")
        gateway = server.ArmMotionGateway(lambda frame: len(frame))
        config = type("Config", (), {"YOLO_MODE": True})()
        service = server._service(gateway, config)
        self.assertTrue(service.snapshot()["motion_enabled"])
        self.assertTrue(service.admission({"name": "arm.jog_joint"}))

    def test_process_owned_gateway_keeps_rpa2_sequence_across_computer_sessions(self):
        sys.modules.pop("arm_command_server", None)
        server = importlib.import_module("arm_command_server")
        writes = []
        gateway = server.ArmMotionGateway(writes.append)
        config = type("Config", (), {"YOLO_MODE": False})()
        command = {
            "version": 1,
            "kind": "command",
            "message_id": "computer-1",
            "sequence": 1,
            "target": "arm",
            "name": "arm.ping",
            "ttl_ms": 1000,
            "payload": {},
        }
        first = server._service(gateway, config)
        first.feed_computer(encode_message(command))
        first.feed_uart(encode_frame("RPA2", "PONG", 1, 0, "protocol=2"))
        command["message_id"] = "computer-2"
        server._service(gateway, config).feed_computer(encode_message(command))
        self.assertEqual([decode_frame(frame)["sequence"] for frame in writes], [1, 2])

    def test_gateway_start_sequence_is_bounded_and_time_derived(self):
        sys.modules.pop("arm_command_server", None)
        server = importlib.import_module("arm_command_server")
        self.assertEqual(server._initial_downstream_sequence(lambda: 1234567890.9), 1234567890)
        self.assertEqual(server._initial_downstream_sequence(lambda: -1), 1)
        self.assertEqual(server._initial_downstream_sequence(lambda: 9999999999), 2147483647)


if __name__ == "__main__":
    unittest.main()
