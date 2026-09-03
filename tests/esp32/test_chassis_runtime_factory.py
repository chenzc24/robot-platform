import pathlib
import sys
import types
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "protocol"))
sys.path.insert(0, str(ROOT / "src/esp32/app"))

from chassis_runtime_factory import NoMotionChassis, make_l2_service
from chassis_tcp_v3 import decode_message, encode_message


class Transport:
    def __init__(self): self.writes = []
    def write(self, data): self.writes.append(data); return len(data)


class ChassisRuntimeFactoryTests(unittest.TestCase):
    def test_l2_service_has_no_motor_or_can_dependency_and_denies_authentication_without_local_secret(self):
        transport = Transport()
        config = types.SimpleNamespace(RUNTIME_HEALTH_TIMEOUT_MS=2000)
        with patch.dict(sys.modules, {"device_config": config}), patch(
            "chassis_runtime_factory.runtime_credential", return_value=None
        ):
            service = make_l2_service(transport)
        self.assertIsInstance(service.chassis, NoMotionChassis)
        service.feed(encode_message("HELLO", 1, 1000, {"client": "test", "credential": "wrong-credential-0001"}))
        self.assertEqual(decode_message(transport.writes[-1])["payload"]["code"], "authentication_failed")
        self.assertFalse(service.motion_permitted)
