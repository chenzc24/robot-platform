"""Local end-to-end tests for the computer RCP/TCP v2 client and router."""

import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "protocol"))
sys.path.insert(0, str(ROOT / "src/esp32/app"))
sys.path.insert(0, str(ROOT / "src/console"))

from chassis_motion_tcp_client import (
    ChassisMotionTcpClient,
    ChassisMotionTcpRejected,
    ChassisMotionTcpUnknown,
)
from chassis_motion_tcp_service import (
    ChassisMotionTcpService,
    fixed_credential_verifier,
)
from chassis_tcp_v2 import decode_message, encode_message
from chassis_tcp_v2 import MAX_SEQUENCE
from control_lease import ControlLease
from motion_router import DualSessionMotionRouter, MotionRouterError


CREDENTIAL = "test-credential-0001"


class FakeChassis:
    def __init__(self):
        self.state = "disabled"
        self.events = []

    def enable_motors(self):
        self.events.append("enable")
        self.state = "enabled_stopped"

    def drive(self, vx, vy, omega):
        self.events.append((vx, vy, omega))
        self.state = "moving"

    def stop(self):
        self.events.append("stop")
        if self.state in ("enabled_stopped", "moving"):
            self.state = "enabled_stopped"

    def disable(self):
        self.events.append("disable")
        self.state = "disabled"


class LoopbackConnection:
    def __init__(self, motion_permitted=True):
        self.responses = []
        self.sent = []
        self.chassis = FakeChassis()
        self.service = ChassisMotionTcpService(
            self,
            self.chassis,
            ControlLease(),
            authorize=fixed_credential_verifier(CREDENTIAL),
            motion_permitted=motion_permitted,
        )

    def write(self, data):
        self.responses.append(bytes(data))
        return len(data)

    def send(self, data):
        self.sent.append(bytes(data))
        self.service.feed(data)
        return len(data)

    def recv(self, _size):
        return self.responses.pop(0) if self.responses else b""


class ChassisMotionTcpClientTests(unittest.TestCase):
    def test_authenticated_owned_motion_lifecycle_is_correlated(self):
        connection = LoopbackConnection()
        client = ChassisMotionTcpClient(connection)
        self.assertEqual(client.hello("console", CREDENTIAL)["type"], "WELCOME")
        self.assertEqual(client.acquire(1000)["type"], "DONE")
        self.assertEqual(client.enable()["payload"]["state"], "enabled_stopped")
        result = client.velocity(100, 0, 0, 250, 500)
        self.assertEqual(result["type"], "DONE")
        self.assertEqual(result["payload"]["command"], "VELOCITY")
        self.assertEqual(len(connection.sent), 4)

    def test_authentication_rejection_is_explicit(self):
        client = ChassisMotionTcpClient(LoopbackConnection())
        with self.assertRaisesRegex(ChassisMotionTcpRejected, "authentication_failed") as raised:
            client.hello("console", "wrong-credential-01")
        self.assertTrue(raised.exception.explicit_rejection)

    def test_state_changing_timeout_is_unknown_and_not_retried(self):
        class TimeoutConnection:
            def __init__(self):
                self.send_calls = 0
                self.recv_calls = 0

            def send(self, data):
                self.send_calls += 1
                return len(data)

            def recv(self, _size):
                self.recv_calls += 1
                raise TimeoutError("timed_out")

        connection = TimeoutConnection()
        client = ChassisMotionTcpClient(connection)
        with self.assertRaisesRegex(ChassisMotionTcpUnknown, "outcome_unknown"):
            client.stop()
        self.assertEqual(connection.send_calls, 1)
        self.assertEqual(connection.recv_calls, 1)

    def test_done_without_ack_is_unknown_for_motion(self):
        class InvalidLifecycleConnection:
            def send(self, data):
                self.request = decode_message(data)
                return len(data)

            def recv(self, _size):
                return encode_message(
                    "DONE",
                    self.request["sequence"],
                    0,
                    {"command": self.request["type"], "state": "disabled"},
                )

        with self.assertRaisesRegex(ChassisMotionTcpUnknown, "outcome_unknown"):
            ChassisMotionTcpClient(InvalidLifecycleConnection()).disable()

    def test_sequence_exhaustion_requires_a_fresh_connection(self):
        connection = LoopbackConnection()
        client = ChassisMotionTcpClient(connection)
        client.hello("console", CREDENTIAL)
        client.next_sequence = MAX_SEQUENCE
        client.ping()
        with self.assertRaisesRegex(Exception, "sequence_exhausted"):
            client.ping()


class FakeSession:
    def __init__(self, name):
        self.name = name
        self.calls = []

    def __getattr__(self, method):
        def call(*args):
            self.calls.append((method, args))
            return {"session": self.name, "method": method}

        return call


def message(target, name, payload=None, ttl_ms=1000):
    return {
        "message_id": "message-1",
        "target": target,
        "name": name,
        "ttl_ms": ttl_ms,
        "payload": {} if payload is None else payload,
    }


class DualSessionMotionRouterTests(unittest.TestCase):
    def test_chassis_goes_direct_and_arm_goes_only_to_maixcam_session(self):
        chassis = FakeSession("esp32")
        arm = FakeSession("maixcam")
        router = DualSessionMotionRouter(chassis, arm, admission=lambda *_args: True)
        chassis_result = router.dispatch(message("chassis", "chassis.status"))
        arm_result = router.dispatch(message("arm", "arm.status"))
        self.assertEqual(chassis_result["result"]["session"], "esp32")
        self.assertEqual(arm_result["result"]["session"], "maixcam")
        self.assertEqual([item[0] for item in chassis.calls], ["status"])
        self.assertEqual([item[0] for item in arm.calls], ["status"])

    def test_motion_requires_admission_and_never_cross_routes(self):
        chassis = FakeSession("esp32")
        arm = FakeSession("maixcam")
        router = DualSessionMotionRouter(chassis, arm)
        velocity = message(
            "chassis",
            "chassis.velocity",
            {"vx_mm_s": 100, "vy_mm_s": 0, "omega_mrad_s": 0, "hold_ms": 250},
            500,
        )
        with self.assertRaisesRegex(MotionRouterError, "admission_unavailable"):
            router.dispatch(velocity)
        self.assertEqual(chassis.calls, [])
        self.assertEqual(arm.calls, [])

    def test_target_and_payload_mismatch_are_rejected_before_downstream(self):
        chassis = FakeSession("esp32")
        arm = FakeSession("maixcam")
        router = DualSessionMotionRouter(chassis, arm, admission=lambda *_args: True)
        with self.assertRaisesRegex(MotionRouterError, "target_mismatch"):
            router.dispatch(message("arm", "chassis.stop"))
        with self.assertRaisesRegex(MotionRouterError, "invalid_payload_fields"):
            router.dispatch(message("chassis", "chassis.stop", {"extra": True}))
        self.assertEqual(chassis.calls, [])
        self.assertEqual(arm.calls, [])


if __name__ == "__main__":
    unittest.main()
