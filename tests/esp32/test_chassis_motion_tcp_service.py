"""Fail-closed local tests for the ESP32 RCP/TCP v2 motion service."""

import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "protocol"))
sys.path.insert(0, str(ROOT / "src/esp32/app"))

from chassis_motion_tcp_service import (
    ChassisMotionTcpRuntime,
    ChassisMotionTcpService,
    fixed_credential_verifier,
)
from chassis_tcp_v2 import decode_message, encode_message
from control_lease import ControlLease


CREDENTIAL = "test-credential-0001"


class FakeClock:
    def __init__(self):
        self.now = 1000

    def __call__(self):
        return self.now

    def advance(self, milliseconds):
        self.now += milliseconds


class FakeTransport:
    def __init__(self, short_write=False):
        self.writes = []
        self.short_write = short_write

    def write(self, data):
        self.writes.append(bytes(data))
        return len(data) - 1 if self.short_write else len(data)


class FakeChassis:
    def __init__(self, fail_drive=False, fail_stop=False):
        self.state = "disabled"
        self.events = []
        self.fail_drive = fail_drive
        self.fail_stop = fail_stop

    def enable_motors(self):
        self.events.append("enable")
        self.state = "enabled_stopped"

    def drive(self, vx, vy, omega):
        self.events.append(("drive", vx, vy, omega))
        if self.fail_drive:
            raise OSError("fake_bus_failure")
        self.state = "moving"

    def stop(self):
        self.events.append("stop")
        if self.fail_stop:
            raise OSError("fake_stop_failure")
        if self.state in ("enabled_stopped", "moving"):
            self.state = "enabled_stopped"

    def disable(self):
        self.events.append("disable")
        self.state = "disabled"


class ServiceHarness:
    def __init__(
        self,
        motion_permitted=False,
        authorize=True,
        short_write=False,
        fail_drive=False,
        fail_stop=False,
    ):
        self.clock = FakeClock()
        self.transport = FakeTransport(short_write)
        self.chassis = FakeChassis(fail_drive, fail_stop)
        verifier = fixed_credential_verifier(CREDENTIAL) if authorize else None
        self.service = ChassisMotionTcpService(
            self.transport,
            self.chassis,
            ControlLease(self.clock),
            authorize=verifier,
            motion_permitted=motion_permitted,
            clock_ms=self.clock,
        )
        self.sequence = 1

    def feed(self, message_type, payload=None, ttl_ms=1000):
        sequence = self.sequence
        self.sequence += 1
        self.service.feed(
            encode_message(message_type, sequence, ttl_ms, payload),
            received_at_ms=self.clock.now,
            now_ms=self.clock.now,
        )
        return [
            decode_message(item)
            for item in self.transport.writes
            if decode_message(item)["sequence"] == sequence
        ]

    def authenticate(self):
        return self.feed(
            "HELLO", {"client": "console", "credential": CREDENTIAL}
        )


class ChassisMotionTcpServiceTests(unittest.TestCase):
    def test_default_denies_authentication_and_does_not_retain_credential(self):
        harness = ServiceHarness(authorize=False)
        responses = harness.authenticate()
        self.assertEqual(responses[-1]["payload"]["code"], "authentication_failed")
        self.assertFalse(harness.service.authenticated)
        self.assertIsNone(harness.service._last_fingerprint)
        self.assertNotIn(CREDENTIAL, repr(harness.service.__dict__))
        self.assertTrue(harness.service.close_required)

    def test_authenticated_status_reports_motion_disabled_without_hardware_calls(self):
        harness = ServiceHarness()
        self.assertEqual(harness.authenticate()[0]["type"], "WELCOME")
        state = harness.feed("STATUS", {})[0]
        self.assertEqual(state["type"], "STATE")
        self.assertFalse(state["payload"]["motion_permitted"])
        self.assertTrue(state["payload"]["authenticated"])
        self.assertEqual(harness.chassis.events, [])

    def test_motion_disabled_rejects_enable_after_valid_acquire(self):
        harness = ServiceHarness()
        harness.authenticate()
        harness.feed("ACQUIRE", {"lease_ms": 1000})
        response = harness.feed("ENABLE", {})[-1]
        self.assertEqual(response["type"], "ERROR")
        self.assertEqual(response["payload"]["code"], "motion_disabled")
        self.assertEqual(harness.chassis.events, [])

    def test_bounded_velocity_and_hold_expiry_stop_and_disable_locally(self):
        harness = ServiceHarness(motion_permitted=True)
        harness.authenticate()
        harness.feed("ACQUIRE", {"lease_ms": 1000})
        harness.feed("ENABLE", {})
        responses = harness.feed(
            "VELOCITY",
            {"vx_mm_s": 100, "vy_mm_s": 0, "omega_mrad_s": 0, "hold_ms": 250},
            500,
        )
        self.assertEqual([item["type"] for item in responses], ["ACK", "DONE"])
        self.assertEqual(harness.chassis.state, "moving")
        harness.clock.advance(250)
        event = harness.service.poll_safety()
        self.assertEqual(event["event"], "velocity_hold_expired")
        self.assertEqual(harness.chassis.events[-2:], ["stop", "disable"])
        self.assertEqual(harness.chassis.state, "disabled")

    def test_runtime_velocity_limits_reject_before_any_drive(self):
        harness = ServiceHarness(motion_permitted=True)
        harness.service.max_linear_mm_s = 50
        harness.service.max_omega_mrad_s = 100
        harness.service.max_hold_ms = 200
        harness.authenticate()
        harness.feed("ACQUIRE", {"lease_ms": 1000})
        harness.feed("ENABLE", {})
        for payload, code in (
            ({"vx_mm_s": 51, "vy_mm_s": 0, "omega_mrad_s": 0, "hold_ms": 200}, "linear_speed_limited"),
            ({"vx_mm_s": 0, "vy_mm_s": 0, "omega_mrad_s": 101, "hold_ms": 200}, "angular_speed_limited"),
            ({"vx_mm_s": 50, "vy_mm_s": 0, "omega_mrad_s": 0, "hold_ms": 201}, "hold_duration_limited"),
        ):
            response = harness.feed("VELOCITY", payload, 500)[-1]
            self.assertEqual(response["payload"]["code"], code)
        self.assertFalse(any(isinstance(item, tuple) for item in harness.chassis.events))

    def test_heartbeat_renews_lease_then_expiry_stops_locally(self):
        harness = ServiceHarness(motion_permitted=True)
        harness.authenticate()
        harness.feed("ACQUIRE", {"lease_ms": 300})
        harness.feed("ENABLE", {})
        harness.clock.advance(200)
        harness.feed("HEARTBEAT", {"lease_ms": 300})
        harness.clock.advance(299)
        self.assertIsNone(harness.service.poll_safety())
        harness.clock.advance(1)
        event = harness.service.poll_safety()
        self.assertEqual(event["event"], "lease_expired")
        self.assertEqual(harness.chassis.state, "disabled")

    def test_identical_duplicate_replays_without_reexecuting_velocity(self):
        harness = ServiceHarness(motion_permitted=True)
        harness.authenticate()
        harness.feed("ACQUIRE", {"lease_ms": 1000})
        harness.feed("ENABLE", {})
        request = encode_message(
            "VELOCITY",
            4,
            500,
            {"vx_mm_s": 100, "vy_mm_s": 0, "omega_mrad_s": 0, "hold_ms": 250},
        )
        harness.service.feed(request, now_ms=harness.clock.now)
        first_drive_count = len([item for item in harness.chassis.events if isinstance(item, tuple)])
        harness.service.feed(request, now_ms=harness.clock.now)
        second_drive_count = len([item for item in harness.chassis.events if isinstance(item, tuple)])
        self.assertEqual(first_drive_count, second_drive_count)
        conflict = encode_message(
            "VELOCITY",
            4,
            500,
            {"vx_mm_s": 101, "vy_mm_s": 0, "omega_mrad_s": 0, "hold_ms": 250},
        )
        harness.service.feed(conflict, now_ms=harness.clock.now)
        self.assertEqual(
            decode_message(harness.transport.writes[-1])["payload"]["code"],
            "sequence_conflict",
        )

    def test_malformed_authenticated_stream_and_disconnect_fail_safe(self):
        harness = ServiceHarness(motion_permitted=True)
        harness.authenticate()
        harness.feed("ACQUIRE", {"lease_ms": 1000})
        harness.feed("ENABLE", {})
        harness.service.feed(b"invalid\n")
        self.assertEqual(harness.chassis.events[-2:], ["stop", "disable"])
        self.assertTrue(harness.service.close_required)

        other = ServiceHarness(motion_permitted=True)
        other.authenticate()
        other.feed("ACQUIRE", {"lease_ms": 1000})
        other.feed("ENABLE", {})
        other.service.on_disconnect()
        self.assertEqual(other.chassis.events[-2:], ["stop", "disable"])
        self.assertFalse(other.service.authenticated)
        self.assertEqual(other.service.last_sequence, 0)

        replacement = FakeTransport()
        other.service.reset_for_connection(replacement)
        other.service.feed(
            encode_message(
                "HELLO",
                1,
                1000,
                {"client": "console", "credential": CREDENTIAL},
            )
        )
        self.assertEqual(decode_message(replacement.writes[-1])["type"], "WELCOME")

    def test_failed_stop_still_attempts_disable_and_reports_safe_output_failure(self):
        harness = ServiceHarness(motion_permitted=True, fail_stop=True)
        harness.authenticate()
        harness.feed("ACQUIRE", {"lease_ms": 300})
        harness.clock.advance(300)
        event = harness.service.poll_safety()
        self.assertEqual(event["event"], "watchdog_stop_failed")
        self.assertEqual(harness.chassis.events[-2:], ["stop", "disable"])
        self.assertEqual(harness.service.service_state, "fault")

    def test_malformed_batch_does_not_execute_following_valid_command(self):
        harness = ServiceHarness(motion_permitted=True)
        harness.authenticate()
        harness.feed("ACQUIRE", {"lease_ms": 1000})
        next_sequence = harness.sequence
        valid = encode_message("ENABLE", next_sequence, 1000, {})
        harness.service.feed(b"invalid\n" + valid)
        self.assertNotIn("enable", harness.chassis.events)
        self.assertTrue(harness.service.close_required)

    def test_execution_and_short_write_faults_attempt_safe_output(self):
        harness = ServiceHarness(motion_permitted=True, fail_drive=True)
        harness.authenticate()
        harness.feed("ACQUIRE", {"lease_ms": 1000})
        harness.feed("ENABLE", {})
        response = harness.feed(
            "VELOCITY",
            {"vx_mm_s": 100, "vy_mm_s": 0, "omega_mrad_s": 0, "hold_ms": 250},
            500,
        )[-1]
        self.assertEqual(response["payload"]["code"], "execution_failed")
        self.assertEqual(harness.chassis.events[-2:], ["stop", "disable"])

        short = ServiceHarness(short_write=True)
        with self.assertRaisesRegex(OSError, "tcp_short_write"):
            short.authenticate()
        self.assertEqual(short.chassis.events[-2:], ["stop", "disable"])


class RuntimeConnection(FakeTransport):
    def __init__(self, chunks):
        FakeTransport.__init__(self)
        self.chunks = list(chunks)

    def recv(self, _size):
        return self.chunks.pop(0) if self.chunks else None


class ChassisMotionTcpRuntimeTests(unittest.TestCase):
    def test_idle_read_timeout_keeps_session_and_watchdog_polling(self):
        class IdleConnection(FakeTransport):
            def recv(self, _size):
                raise TimeoutError("idle")

        clock = FakeClock()
        connection = IdleConnection()
        chassis = FakeChassis()
        service = ChassisMotionTcpService(
            connection,
            chassis,
            ControlLease(clock),
            authorize=fixed_credential_verifier(CREDENTIAL),
            clock_ms=clock,
        )
        runtime = ChassisMotionTcpRuntime(service, connection)
        self.assertIsNone(runtime.poll_once())
        self.assertFalse(service.close_required)
        self.assertEqual(chassis.events, [])

    def test_connection_close_invokes_local_safe_output(self):
        clock = FakeClock()
        connection = RuntimeConnection([b""])
        chassis = FakeChassis()
        service = ChassisMotionTcpService(
            connection,
            chassis,
            ControlLease(clock),
            authorize=fixed_credential_verifier(CREDENTIAL),
            clock_ms=clock,
        )
        runtime = ChassisMotionTcpRuntime(service, connection)
        with self.assertRaisesRegex(OSError, "connection_lost"):
            runtime.poll_once()
        self.assertEqual(chassis.events[-2:], ["stop", "disable"])


if __name__ == "__main__":
    unittest.main()
