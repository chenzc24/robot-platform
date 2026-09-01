"""Polling composition for one computer client and one UART0 owner."""

import time


class ArmCommandRuntime:
    def __init__(self, service, computer_connection, uart, sleep_ms=5):
        self.service, self.computer_connection, self.uart, self.sleep_ms = service, computer_connection, uart, sleep_ms

    def poll_once(self):
        try:
            data = self.computer_connection.recv(4096)
        except Exception as error:
            code = getattr(error, "errno", None)
            if not isinstance(error, TimeoutError) and code not in (11, 110, 116, 10035):
                raise
            data = None
        if data == b"": raise OSError("computer_disconnected")
        reply = self.service.feed_computer(data) if data else b""
        uart_data = self.uart.read()
        if uart_data:
            reply += self.service.feed_uart(uart_data)
        reply += self.service.poll()
        if reply:
            sent = 0
            while sent < len(reply):
                count = self.computer_connection.send(reply[sent:])
                if not count: raise OSError("computer_short_write")
                sent += count

    def run_forever(self):
        while True:
            self.poll_once()
            time.sleep(self.sleep_ms / 1000.0)
