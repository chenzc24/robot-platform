"""Safety and protocol tests for the narrow ESP32 WebREPL reset tool."""

from contextlib import redirect_stderr, redirect_stdout
import io
import pathlib
import socket
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
ESP32_TOOLS = ROOT / "tools" / "esp32"
sys.path.insert(0, str(ESP32_TOOLS))

import webrepl_reset
import webrepl_probe


class FakeSocket:
    def __init__(self):
        self.timeout = None
        self.address = None
        self.closed = False

    def settimeout(self, timeout):
        self.timeout = timeout

    def connect(self, address):
        self.address = address

    def close(self):
        self.closed = True

    def recv(self, _size):
        return b""


class TimeoutSocket(FakeSocket):
    def recv(self, _size):
        raise TimeoutError


class FakeWebSocket:
    def __init__(self):
        self.read_buffer = bytearray(b"KeyboardInterrupt\r\n>>> ")
        self.writes = []
        self.ioctl_calls = []

    def read(self, size, text_ok=False):
        del text_ok
        result = bytes(self.read_buffer[:size])
        del self.read_buffer[:size]
        return result

    def write(self, data, frame):
        self.writes.append((data, frame))

    def ioctl(self, request, value):
        self.ioctl_calls.append((request, value))


class FakeClient:
    WEBREPL_FRAME_TXT = 0x81

    def __init__(self):
        self.ws = FakeWebSocket()
        self.handshake_socket = None
        self.login_password = None

    def client_handshake(self, connection):
        self.handshake_socket = connection

    def websocket(self, _connection):
        return self.ws

    def login(self, _ws, password):
        self.login_password = password

    def get_ver(self, _ws):
        return (1, 27, 0)


class WebReplResetTests(unittest.TestCase):
    def test_password_is_loaded_from_an_explicit_ignored_style_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "secrets.py"
            path.write_text('WEBREPL_PASSWORD = "local1234"\n', encoding="utf-8")
            self.assertEqual(webrepl_reset.load_password(path), "local1234")

    def test_reset_sends_only_interrupt_and_hard_reset(self):
        connection = FakeSocket()
        client = FakeClient()
        version, disconnect_confirmed = webrepl_reset.reset_device(
            "192.0.2.30",
            "local1234",
            client_module=client,
            socket_factory=lambda: connection,
            address_resolver=lambda *_args: [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.0.2.30", 8266))
            ],
        )
        self.assertEqual(version, (1, 27, 0))
        self.assertTrue(disconnect_confirmed)
        self.assertEqual(client.login_password, "local1234")
        self.assertEqual(
            [item[0] for item in client.ws.writes],
            [webrepl_reset.INTERRUPT_COMMAND, webrepl_reset.RESET_COMMAND],
        )
        self.assertEqual(client.ws.ioctl_calls, [(9, 2)])
        self.assertTrue(connection.closed)

    def test_reset_reports_an_unconfirmed_socket_disconnect(self):
        connection = TimeoutSocket()
        client = FakeClient()
        version, disconnect_confirmed = webrepl_reset.reset_device(
            "192.0.2.30",
            "local1234",
            client_module=client,
            socket_factory=lambda: connection,
            address_resolver=lambda *_args: [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.0.2.30", 8266))
            ],
        )
        self.assertEqual(version, (1, 27, 0))
        self.assertFalse(disconnect_confirmed)
        self.assertTrue(connection.closed)

    def test_execute_lines_rejects_multiline_input_and_closes_connection(self):
        connection = FakeSocket()
        client = FakeClient()
        with self.assertRaises(ValueError):
            webrepl_reset.execute_lines(
                "192.0.2.30",
                "local1234",
                ("print('safe')\nprint('unexpected')",),
                client_module=client,
                socket_factory=lambda: connection,
                address_resolver=lambda *_args: [
                    (
                        socket.AF_INET,
                        socket.SOCK_STREAM,
                        0,
                        "",
                        ("192.0.2.30", 8266),
                    )
                ],
            )
        self.assertTrue(connection.closed)

    def test_probe_parser_returns_only_explicit_markers(self):
        responses = [
            b"print('PROBE_MODE', 'ps2')\r\nPROBE_MODE ps2\r\n>>> ",
            b"noise\r\nPROBE_PS2 65 90 0 128 128 128 128\r\n>>> ",
        ]
        self.assertEqual(
            webrepl_probe.marker_lines(responses),
            ["PROBE_MODE ps2", "PROBE_PS2 65 90 0 128 128 128 128"],
        )

    def test_probe_diagnostics_exclude_echoed_commands(self):
        responses = [
            b"KeyboardInterrupt\r\n>>> ",
            b"raise ValueError('probe')\r\nTraceback (most recent call last):\r\n"
            b"ValueError: probe\r\n>>> ",
        ]
        self.assertEqual(
            webrepl_probe.diagnostic_lines(responses),
            [
                {
                    "response_index": 1,
                    "message": "Traceback (most recent call last):",
                },
                {"response_index": 1, "message": "ValueError: probe"},
            ],
        )

    def test_main_never_prints_the_local_password(self):
        with tempfile.TemporaryDirectory() as directory:
            secret_path = pathlib.Path(directory) / "secrets.py"
            secret_path.write_text(
                'WEBREPL_PASSWORD = "hidden123"\n',
                encoding="utf-8",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()

            def fake_reset(_host, password, port):
                self.assertEqual(password, "hidden123")
                self.assertEqual(port, 8266)
                return (1, 27, 0), True

            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = webrepl_reset.main(
                    [
                        "--host",
                        "192.0.2.30",
                        "--secret-path",
                        str(secret_path),
                    ],
                    reset_func=fake_reset,
                )
            self.assertEqual(result, 0)
            self.assertNotIn("hidden123", stdout.getvalue())
            self.assertNotIn("hidden123", stderr.getvalue())
            self.assertIn('"action": "reset_sent"', stdout.getvalue())
            self.assertIn('"disconnect_confirmed": true', stdout.getvalue())
if __name__ == "__main__":
    unittest.main()
