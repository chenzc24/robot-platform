"""Fail-closed tests for the ESP32 RCP1/TCP non-motion service."""

import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "protocol"))
sys.path.insert(0, str(ROOT / "src/esp32/app"))

from chassis_tcp import decode_message, encode_message
from chassis_tcp_probe import run_probe
from chassis_tcp_service import ChassisTcpService


class FakeTransport:
    def __init__(self, short_write=False):
        self.writes = []
        self.short_write = short_write

    def write(self, data):
        self.writes.append(bytes(data))
        return len(data) - 1 if self.short_write else len(data)


class ChassisTcpServiceTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.service = ChassisTcpService(self.transport)

    def _feed(self, message_type, sequence, payload=None):
        return self.service.feed(
            encode_message(message_type, sequence, 1000, payload)
        )

    def test_complete_exchange_reports_safe_non_motion_state(self):
        self._feed("HELLO", 1, {"client": "console"})
        self._feed("PING", 2, {})
        self._feed("STATUS", 3, {})
        responses = [decode_message(item) for item in self.transport.writes]
        self.assertEqual(
            [item["type"] for item in responses], ["WELCOME", "PONG", "STATE"]
        )
        snapshot = self.service.status_snapshot()
        self.assertTrue(snapshot["complete"])
        self.assertFalse(snapshot["motion_enabled"])
        self.assertEqual(snapshot["requests_handled"], 3)

    def test_session_is_required_before_ping(self):
        self._feed("PING", 1, {})
        response = decode_message(self.transport.writes[-1])
        self.assertEqual(response["type"], "ERROR")
        self.assertEqual(response["payload"]["code"], "session_required")
        self.assertEqual(self.service.requests_handled, 0)

    def test_duplicate_replay_conflict_and_out_of_order(self):
        hello = encode_message("HELLO", 2, 1000, {"client": "console"})
        self.service.feed(hello)
        first_response = self.transport.writes[-1]
        self.assertIn("duplicate_replayed", self.service.feed(hello))
        self.assertEqual(self.transport.writes[-1], first_response)
        self.service.feed(encode_message("HELLO", 2, 1000, {"client": "operator"}))
        self.assertEqual(
            decode_message(self.transport.writes[-1])["payload"]["code"],
            "sequence_conflict",
        )
        self.service.feed(encode_message("PING", 1, 1000, {}))
        self.assertEqual(
            decode_message(self.transport.writes[-1])["payload"]["code"],
            "out_of_order",
        )

    def test_second_hello_and_response_direction_are_rejected(self):
        self._feed("HELLO", 1, {"client": "console"})
        self._feed("HELLO", 2, {"client": "console"})
        self.assertEqual(
            decode_message(self.transport.writes[-1])["payload"]["code"],
            "session_started",
        )
        self.service.feed(
            encode_message("PONG", 3, 0, {"protocol": 1})
        )
        self.assertEqual(
            decode_message(self.transport.writes[-1])["payload"]["code"],
            "unsupported_direction",
        )

    def test_malformed_input_does_not_produce_a_response(self):
        self.service.feed(b"invalid\n")
        self.assertEqual(self.transport.writes, [])
        self.assertEqual(self.service.error_code, "invalid_json")

    def test_short_write_enters_fault(self):
        service = ChassisTcpService(FakeTransport(short_write=True))
        with self.assertRaises(OSError):
            service.feed(encode_message("HELLO", 1, 1000, {"client": "console"}))
        self.assertEqual(service.state, "fault")


class FakeConnection:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.sent = []
        self.timeout = None
        self.closed = False

    def settimeout(self, value):
        self.timeout = value

    def recv(self, _size):
        return self.chunks.pop(0) if self.chunks else b""

    def send(self, data):
        self.sent.append(bytes(data))
        return len(data)

    def close(self):
        self.closed = True


class FakeListener:
    def __init__(self, connection, accept_error=None):
        self.connection = connection
        self.accept_error = accept_error
        self.bound = None
        self.timeout = None
        self.closed = False

    def setsockopt(self, *_args):
        pass

    def bind(self, address):
        self.bound = address

    def listen(self, _backlog):
        pass

    def settimeout(self, value):
        self.timeout = value

    def accept(self):
        if self.accept_error is not None:
            raise self.accept_error
        return self.connection, ("computer", 50000)

    def close(self):
        self.closed = True


class FakeSocketModule:
    AF_INET = 2
    SOCK_STREAM = 1
    SOL_SOCKET = 1
    SO_REUSEADDR = 2

    def __init__(self, connection, accept_error=None):
        self.listener = FakeListener(connection, accept_error)

    def socket(self, _family, _kind):
        return self.listener


class ChassisTcpProbeTests(unittest.TestCase):
    def test_probe_accepts_one_complete_client_and_closes_resources(self):
        requests = b"".join(
            (
                encode_message("HELLO", 1, 1000, {"client": "console"}),
                encode_message("PING", 2, 1000, {}),
                encode_message("STATUS", 3, 1000, {}),
            )
        )
        connection = FakeConnection([requests])
        socket_module = FakeSocketModule(connection)
        result = run_probe(socket_module=socket_module)
        self.assertTrue(result["complete"])
        self.assertFalse(result["motion_enabled"])
        self.assertEqual(socket_module.listener.bound, ("0.0.0.0", 8765))
        self.assertTrue(connection.closed)
        self.assertTrue(socket_module.listener.closed)

    def test_accept_timeout_is_bounded_and_closes_listener(self):
        socket_module = FakeSocketModule(None, OSError("accept_timeout"))
        with self.assertRaisesRegex(OSError, "accept_timeout"):
            run_probe(accept_timeout_seconds=7, socket_module=socket_module)
        self.assertEqual(socket_module.listener.timeout, 7)
        self.assertTrue(socket_module.listener.closed)

    def test_probe_has_no_motion_imports(self):
        source = (ROOT / "src/esp32/app/chassis_tcp_probe.py").read_text("utf-8")
        for forbidden in ("motor_bus", "chassis_control", "machine.CAN", "ps2"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
