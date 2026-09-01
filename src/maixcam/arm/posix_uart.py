"""Exclusive POSIX UART adapter that does not import the Maix protocol stack."""

import os

try:
    import termios
except ImportError:
    termios = None


class UartConfigurationError(ValueError):
    """Describe an unsafe or unsupported diagnostic UART configuration."""


class PosixUartTransport:
    """Open the confirmed arm UART as non-blocking 115200 8N1."""

    def __init__(
        self,
        device="/dev/ttyS0",
        baud=115200,
        os_module=None,
        termios_module=None,
    ):
        if device != "/dev/ttyS0":
            raise UartConfigurationError("arm diagnostic requires /dev/ttyS0")
        if baud != 115200:
            raise UartConfigurationError("arm diagnostic requires 115200 baud")
        self.device = device
        self.baud = baud
        self._os = os_module or os
        self._termios = termios_module or termios
        if self._termios is None:
            raise RuntimeError("POSIX termios is unavailable")
        self._fd = self._os.open(
            device,
            self._os.O_RDWR | self._os.O_NOCTTY | self._os.O_NONBLOCK,
        )
        try:
            self._configure()
        except Exception:
            self._os.close(self._fd)
            self._fd = None
            raise

    def _configure(self):
        settings = self._termios.tcgetattr(self._fd)
        settings[0] = 0
        settings[1] = 0
        settings[2] = (
            self._termios.CLOCAL | self._termios.CREAD | self._termios.CS8
        )
        settings[3] = 0
        settings[4] = self._termios.B115200
        settings[5] = self._termios.B115200
        settings[6][self._termios.VMIN] = 0
        settings[6][self._termios.VTIME] = 0
        self._termios.tcsetattr(
            self._fd,
            self._termios.TCSANOW,
            settings,
        )
        self._termios.tcflush(self._fd, self._termios.TCIOFLUSH)

    def write(self, data):
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("UART writes must be bytes")
        return self._os.write(self._fd, bytes(data))

    def read(self):
        try:
            return self._os.read(self._fd, 256)
        except BlockingIOError:
            return b""

    def close(self):
        if self._fd is not None:
            self._os.close(self._fd)
            self._fd = None
