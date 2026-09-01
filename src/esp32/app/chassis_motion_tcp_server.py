"""One-client MicroPython listener for the direct RCP/TCP v2 chassis service."""

try:
    import usocket as socket
except ImportError:
    import socket

from chassis_motion_tcp_service import ChassisMotionTcpRuntime


class SocketTransport:
    """Make short socket writes visible to the service as an error."""
    def __init__(self, connection): self.connection = connection
    def write(self, data):
        sent = 0
        while sent < len(data):
            count = self.connection.send(data[sent:])
            if not count: raise OSError("connection_closed_during_write")
            sent += count
        return sent


class ChassisMotionTcpServer:
    """Accept exactly one connection at a time; every replacement is a new service."""
    def __init__(self, service_factory, port, bind_address="0.0.0.0", socket_module=None):
        if not callable(service_factory): raise ValueError("service_factory is required")
        if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535: raise ValueError("invalid port")
        self.service_factory, self.port, self.bind_address = service_factory, port, bind_address
        self.socket = socket_module or socket

    def listen(self):
        listener = self.socket.socket(self.socket.AF_INET, self.socket.SOCK_STREAM)
        try:
            listener.setsockopt(self.socket.SOL_SOCKET, self.socket.SO_REUSEADDR, 1)
        except AttributeError:
            pass
        listener.bind((self.bind_address, self.port))
        listener.listen(1)
        return listener

    def run_forever(self):
        listener = self.listen()
        while True:
            connection, _ = listener.accept()
            try:
                connection.settimeout(0.05)
                service = self.service_factory(SocketTransport(connection))
                ChassisMotionTcpRuntime(service, connection).run_forever()
            except Exception:
                # The service has already attempted local safe output for an active session.
                try: connection.close()
                except Exception: pass
