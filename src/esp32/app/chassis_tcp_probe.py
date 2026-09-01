"""Run one bounded non-motion RCP1/TCP server on ESP32."""


DEFAULT_PORT = 8765
DEFAULT_ACCEPT_TIMEOUT_SECONDS = 20
DEFAULT_CLIENT_TIMEOUT_SECONDS = 5


class SocketTransport:
    """Provide complete writes over an accepted MicroPython socket."""

    def __init__(self, connection):
        self.connection = connection

    def write(self, data):
        data = bytes(data)
        sent = 0
        while sent < len(data):
            count = self.connection.send(data[sent:])
            if not count:
                raise OSError("TCP connection closed during write")
            sent += count
        return sent


def _close_quietly(value):
    if value is None:
        return
    try:
        value.close()
    except Exception:
        pass


def run_probe(
    port=DEFAULT_PORT,
    accept_timeout_seconds=DEFAULT_ACCEPT_TIMEOUT_SECONDS,
    client_timeout_seconds=DEFAULT_CLIENT_TIMEOUT_SECONDS,
    socket_module=None,
):
    """Accept one client and return after the fixed non-motion exchange."""
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValueError("port must be in 1024..65535")
    if accept_timeout_seconds <= 0 or client_timeout_seconds <= 0:
        raise ValueError("timeouts must be positive")
    if socket_module is None:
        import socket as socket_module

    from chassis_tcp_service import ChassisTcpService

    listener = None
    connection = None
    try:
        listener = socket_module.socket(socket_module.AF_INET, socket_module.SOCK_STREAM)
        try:
            listener.setsockopt(socket_module.SOL_SOCKET, socket_module.SO_REUSEADDR, 1)
        except (AttributeError, OSError):
            pass
        listener.bind(("0.0.0.0", port))
        listener.listen(1)
        listener.settimeout(accept_timeout_seconds)
        connection, _address = listener.accept()
        connection.settimeout(client_timeout_seconds)
        service = ChassisTcpService(SocketTransport(connection))
        while not service.complete:
            data = connection.recv(256)
            if not data:
                raise OSError("client_disconnected")
            service.feed(data)
            if service.state == "fault":
                raise RuntimeError(service.error_code or "service_fault")
        return service.status_snapshot()
    finally:
        _close_quietly(connection)
        _close_quietly(listener)


if __name__ == "__main__":
    try:
        import ujson as json
    except ImportError:
        import json

    try:
        result = run_probe()
    except Exception as error:
        result = {
            "state": "fault",
            "error_code": str(error),
            "motion_enabled": False,
            "complete": False,
        }
    print(json.dumps(result))
