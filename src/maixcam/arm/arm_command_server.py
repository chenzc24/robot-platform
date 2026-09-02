"""One-client MaixCam server for the arm-only command endpoint.

This program owns UART0 only after an external launcher/ownership guard has
verified and released the Maix launcher. Its default policy rejects motion.
"""

import time

try:
    import usocket as socket
except ImportError:
    import socket

from arm_motion_gateway import ArmMotionGateway
from command_service import ArmCommandService
from command_runtime import ArmCommandRuntime
from motion_link import MAX_SEQUENCE
from posix_uart import PosixUartTransport


def _settings():
    try:
        import arm_service_config as config
    except ImportError:
        import arm_service_config_example as config
    return config


def _deny_motion(_message):
    return False


def _service(gateway, config):
    """Create a computer session while retaining process-owned RPA2 sequencing."""
    permitted = getattr(config, "MOTION_COMMANDS_PERMITTED", False) is True
    return ArmCommandService(gateway, admission=lambda _message: permitted)


def _initial_downstream_sequence(clock=None):
    """Seed a freshly started gateway above typical persisted arm sequences."""
    sequence = int((clock or time.time)())
    return min(MAX_SEQUENCE, max(1, sequence))


def serve_forever(socket_module=None, uart_factory=None):
    config, socket_module = _settings(), socket_module or socket
    uart_factory = uart_factory or PosixUartTransport
    uart = uart_factory(config.UART_DEVICE, config.UART_BAUD)
    gateway = ArmMotionGateway(uart.write, initial_sequence=_initial_downstream_sequence())
    listener = socket_module.socket(socket_module.AF_INET, socket_module.SOCK_STREAM)
    try:
        listener.setsockopt(socket_module.SOL_SOCKET, socket_module.SO_REUSEADDR, 1)
    except AttributeError:
        pass
    listener.bind((config.LISTEN_ADDRESS, config.LISTEN_PORT))
    listener.listen(1)
    try:
        while True:
            connection, _ = listener.accept()
            try:
                connection.settimeout(0.05)
                # Default deny. A future L3 goal must separately supply a reviewed
                # controller policy and computer-side cross-device admission.
                service = _service(gateway, config)
                runtime = ArmCommandRuntime(service, connection, uart)
                runtime.run_forever()
            except Exception:
                try: connection.close()
                except Exception: pass
    finally:
        try: listener.close()
        except Exception: pass
        uart.close()


if __name__ == "__main__":
    serve_forever()
