import pathlib
import sys
import types
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "protocol"))
sys.path.insert(0, str(ROOT / "src/esp32/app"))

from can_runtime import create_can
from chassis_runtime_factory import make_l3_service_factory


class FakeCan:
    NORMAL = 7
    created = []

    def __init__(self, bus_id, mode, baudrate, tx, rx):
        self.arguments = (bus_id, mode, baudrate, tx, rx)
        self.cleared = False
        FakeCan.created.append(self)

    def clear_rx_queue(self):
        self.cleared = True

    def send(self, _data, _identifier, extframe=False):
        return None


class Config:
    CAN_BUS_ID = 0
    CAN_BAUDRATE = 1000000
    CAN_TX_PIN = 8
    CAN_RX_PIN = 18
    L3_MOTION_PERMITTED = False
    L3_MAX_LINEAR_SPEED_MM_S = 50
    L3_MAX_OMEGA_MRAD_S = 100
    L3_MAX_HOLD_MS = 200


class Transport:
    def write(self, data):
        return len(data)


class CanRuntimeTests(unittest.TestCase):
    def setUp(self):
        FakeCan.created = []
        self.esp32 = types.SimpleNamespace(CAN=FakeCan)

    def test_create_can_uses_explicit_legacy_confirmed_parameters(self):
        with patch.dict(sys.modules, {"esp32": self.esp32}):
            can_bus = create_can(Config)
        self.assertIs(can_bus, FakeCan.created[0])
        self.assertEqual(can_bus.arguments, (0, FakeCan.NORMAL, 1000000, 8, 18))
        self.assertTrue(can_bus.cleared)

    def test_invalid_pin_mapping_rejects_before_can_construction(self):
        class Invalid(Config):
            CAN_RX_PIN = 8

        with patch.dict(sys.modules, {"esp32": self.esp32}):
            with self.assertRaisesRegex(ValueError, "must differ"):
                create_can(Invalid)
        self.assertEqual(FakeCan.created, [])

    def test_l3_factory_starts_disabled_and_motion_remains_explicitly_locked(self):
        config_module = types.SimpleNamespace(**{
            name: getattr(Config, name)
            for name in dir(Config)
            if name.isupper()
        })
        with patch.dict(sys.modules, {"esp32": self.esp32, "device_config": config_module}):
            factory = make_l3_service_factory()
            service = factory(Transport())
        self.assertEqual(service.chassis.state, "disabled")
        self.assertFalse(service.motion_permitted)
        self.assertEqual(service.max_linear_mm_s, 50)
        self.assertEqual(service.max_omega_mrad_s, 100)
        self.assertEqual(service.max_hold_ms, 200)
        self.assertGreaterEqual(len(FakeCan.created), 1)
