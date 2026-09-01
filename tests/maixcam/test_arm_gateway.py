"""Fail-closed tests for the MaixCam arm diagnostic gateway."""

import pathlib
import sys
import unittest


ARM_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "maixcam" / "arm"
sys.path.insert(0, str(ARM_DIR))

from arm_gateway import ArmDiagnosticGateway, ArmGatewayError
from link_protocol import encode_frame
from posix_uart import PosixUartTransport, UartConfigurationError


class FakeClock:
    def __init__(self):
        self.value = 10.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class FakeOs:
    O_RDWR = 1
    O_NOCTTY = 2
    O_NONBLOCK = 4

    def __init__(self):
        self.opened = []
        self.writes = []
        self.reads = [b"response"]
        self.closed = []

    def open(self, device, flags):
        self.opened.append((device, flags))
        return 9

    def write(self, fd, data):
        self.writes.append((fd, data))
        return len(data)

    def read(self, fd, size):
        return self.reads.pop(0) if self.reads else b""

    def close(self, fd):
        self.closed.append(fd)


class FakeTermios:
    CLOCAL = 1
    CREAD = 2
    CS8 = 4
    B115200 = 115200
    VMIN = 0
    VTIME = 1
    TCSANOW = 0
    TCIOFLUSH = 2

    def __init__(self):
        self.configured = []
        self.flushed = []

    def tcgetattr(self, fd):
        return [1, 1, 1, 1, 1, 1, [1, 1]]

    def tcsetattr(self, fd, when, settings):
        self.configured.append((fd, when, settings))

    def tcflush(self, fd, queue):
        self.flushed.append((fd, queue))


class ArmGatewayTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.writes = []
        self.gateway = ArmDiagnosticGateway(
            self.writes.append,
            timeout_seconds=1.0,
            clock=self.clock,
        )

    def test_matching_pong_completes_with_round_trip_time(self):
        sequence = self.gateway.request("ping")
        self.clock.advance(0.012)
        self.assertTrue(self.gateway.feed(encode_frame("PONG", sequence)))
        self.assertEqual(self.gateway.state, "ready")
        self.assertEqual(self.gateway.round_trip_ms, 12)
        self.assertIsNone(self.gateway.pending_sequence)

    def test_motion_like_requests_are_rejected_before_uart_write(self):
        for command in ("initialize", "move", "gripper"):
            with self.assertRaisesRegex(ArmGatewayError, "motion_disabled"):
                self.gateway.request(command)
        self.assertEqual(self.writes, [])
        self.assertEqual(self.gateway.state, "safe_idle")

    def test_fixed_step_expects_done_and_can_only_be_requested_once(self):
        sequence = self.gateway.request("fixed_j1_step")
        self.assertTrue(self.gateway.feed(encode_frame("DONE", sequence)))
        self.assertTrue(self.gateway.snapshot()["fixed_step_consumed"])
        with self.assertRaisesRegex(ArmGatewayError, "motion_already_consumed"):
            self.gateway.request_fixed_step()

    def test_only_one_request_can_be_in_flight(self):
        self.gateway.request_ping()
        with self.assertRaisesRegex(ArmGatewayError, "request_in_flight"):
            self.gateway.request_ping()

    def test_timeout_reports_disconnect_and_clears_pending(self):
        self.gateway.request_ping()
        self.clock.advance(1.0)
        self.assertTrue(self.gateway.poll())
        self.assertEqual(self.gateway.state, "disconnected")
        self.assertEqual(self.gateway.error_code, "response_timeout")

    def test_sequence_mismatch_and_crc_failure_do_not_complete(self):
        sequence = self.gateway.request_ping()
        self.assertFalse(self.gateway.feed(encode_frame("PONG", sequence + 1)))
        self.assertEqual(self.gateway.error_code, "sequence_mismatch")
        frame = bytearray(encode_frame("PONG", sequence))
        frame[-2] = ord("0") if frame[-2] != ord("0") else ord("1")
        self.assertFalse(self.gateway.feed(frame))
        self.assertEqual(self.gateway.error_code, "crc_mismatch")
        self.assertEqual(self.gateway.pending_sequence, sequence)

    def test_arm_error_is_reported_without_becoming_ready(self):
        sequence = self.gateway.request_ping()
        response = encode_frame("ERROR", sequence, "motion_disabled")
        self.assertFalse(self.gateway.feed(response))
        self.assertEqual(self.gateway.error_code, "motion_disabled")


class PosixUartTransportTests(unittest.TestCase):
    def test_supported_uart_reads_writes_and_closes(self):
        fake_os = FakeOs()
        fake_termios = FakeTermios()
        transport = PosixUartTransport(
            "/dev/ttyS0", 115200, fake_os, fake_termios
        )
        self.assertEqual(transport.write(b"request"), 7)
        self.assertEqual(transport.read(), b"response")
        transport.close()
        self.assertEqual(fake_os.opened[0][0], "/dev/ttyS0")
        self.assertEqual(fake_os.writes, [(9, b"request")])
        self.assertEqual(fake_os.closed, [9])
        self.assertTrue(fake_termios.configured)

    def test_wrong_device_or_baud_is_rejected_before_open(self):
        for device, baud in (("/dev/ttyS2", 115200), ("/dev/ttyS0", 9600)):
            with self.assertRaises(UartConfigurationError):
                PosixUartTransport(device, baud, FakeOs(), FakeTermios())

    def test_text_write_is_rejected(self):
        transport = PosixUartTransport(
            "/dev/ttyS0", 115200, FakeOs(), FakeTermios()
        )
        with self.assertRaises(TypeError):
            transport.write("request")


if __name__ == "__main__":
    unittest.main()
