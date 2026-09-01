"""End-to-end local tests for the computer RCP1/TCP client."""

import pathlib
import sys
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "protocol"))
sys.path.insert(0, str(ROOT / "src/esp32/app"))
sys.path.insert(0, str(ROOT / "src/console"))

from chassis_tcp import decode_message, encode_message
from chassis_tcp_client import ChassisTcpClient, ChassisTcpClientError
from chassis_tcp_probe import run
from chassis_tcp_service import ChassisTcpService


class LoopbackConnection:
    def __init__(self, close_on_recv=False):
        self.responses = []
        self.closed = False
        self.close_on_recv = close_on_recv
        self.service = ChassisTcpService(self)

    def write(self, data):
        self.responses.append(bytes(data))
        return len(data)

    def send(self, data):
        self.service.feed(data)
        return len(data)

    def recv(self, _size):
        if self.close_on_recv:
            return b""
        return self.responses.pop(0) if self.responses else b""

    def close(self):
        self.closed = True


class ChassisTcpClientTests(unittest.TestCase):
    def test_probe_completes_three_matching_non_motion_exchanges(self):
        result = ChassisTcpClient(LoopbackConnection()).probe()
        self.assertTrue(result["ok"])
        self.assertEqual(result["responses"], ["WELCOME", "PONG", "STATE"])
        self.assertEqual(result["sequences"], [1, 2, 3])
        self.assertFalse(result["motion_enabled"])

    def test_unsupported_type_is_rejected_before_write(self):
        connection = LoopbackConnection()
        client = ChassisTcpClient(connection)
        with self.assertRaisesRegex(ChassisTcpClientError, "unsupported"):
            client.exchange("VELOCITY", {})
        self.assertEqual(connection.service.requests_handled, 0)

    def test_disconnect_before_response_fails(self):
        connection = LoopbackConnection(close_on_recv=True)
        with self.assertRaisesRegex(ChassisTcpClientError, "closed"):
            ChassisTcpClient(connection).exchange(
                "HELLO", {"client": "console"}
            )

    def test_socket_timeout_propagates_without_retry(self):
        class TimeoutConnection:
            def __init__(self):
                self.send_calls = 0
                self.recv_calls = 0

            def send(self, data):
                self.send_calls += 1
                return len(data)

            def recv(self, _size):
                self.recv_calls += 1
                raise TimeoutError("timed out")

        connection = TimeoutConnection()
        with self.assertRaisesRegex(TimeoutError, "timed out"):
            ChassisTcpClient(connection).exchange(
                "HELLO", {"client": "console"}
            )
        self.assertEqual(connection.send_calls, 1)
        self.assertEqual(connection.recv_calls, 1)

    def test_sequence_mismatch_fails_without_retry(self):
        class MismatchConnection:
            def send(self, data):
                self.request = decode_message(data)
                return len(data)

            def recv(self, _size):
                return encode_message(
                    "WELCOME",
                    self.request["sequence"] + 1,
                    0,
                    {"service": "chassis", "motion_enabled": False},
                )

        with self.assertRaisesRegex(ChassisTcpClientError, "sequence_mismatch"):
            ChassisTcpClient(MismatchConnection()).exchange(
                "HELLO", {"client": "console"}
            )

    def test_cli_run_closes_connection(self):
        connection = LoopbackConnection()
        args = types.SimpleNamespace(host="esp32", port=8765, timeout=3.0)
        result = run(args, lambda *_args: connection)
        self.assertTrue(result["ok"])
        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
