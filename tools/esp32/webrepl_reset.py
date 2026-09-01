"""Send one guarded hard reset through the pinned official WebREPL client."""

import argparse
import importlib.util
import json
import pathlib
import runpy
import socket
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_SECRET_PATH = ROOT / "src" / "esp32" / "app" / "secrets.py"
OFFICIAL_CLIENT_PATH = ROOT / ".tools" / "webrepl" / "webrepl_cli.py"
DEFAULT_PORT = 8266
RESET_COMMAND = b"import machine; machine.reset()\r\n"
INTERRUPT_COMMAND = b"\x03"


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="Current ESP32 IPv4 address")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--secret-path",
        type=pathlib.Path,
        default=DEFAULT_SECRET_PATH,
        help=argparse.SUPPRESS,
    )
    return parser


def load_password(path):
    """Load the ignored local password without importing the stdlib secrets module."""
    values = runpy.run_path(str(path))
    password = values.get("WEBREPL_PASSWORD")
    if not isinstance(password, str) or not 4 <= len(password) <= 9:
        raise ValueError("local WEBREPL_PASSWORD is missing or invalid")
    return password


def load_official_client(path=OFFICIAL_CLIENT_PATH):
    if not pathlib.Path(path).is_file():
        raise FileNotFoundError("pinned official WebREPL client is missing")
    spec = importlib.util.spec_from_file_location("pinned_webrepl_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_until(ws, marker, limit=16_384):
    """Read text frames until a REPL marker is observed."""
    received = bytearray()
    while marker not in received:
        chunk = ws.read(1, text_ok=True)
        if not chunk:
            raise ConnectionError("WebREPL closed before the expected prompt")
        received.extend(chunk)
        if len(received) > limit:
            raise RuntimeError("WebREPL prompt was not observed")
    return bytes(received)


def open_session(
    host,
    password,
    port=DEFAULT_PORT,
    client_module=None,
    socket_factory=socket.socket,
    address_resolver=socket.getaddrinfo,
):
    """Open one authenticated WebREPL session and return protocol objects."""
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    client = client_module or load_official_client()
    connection = socket_factory()
    connection.settimeout(8)
    address = address_resolver(
        host,
        port,
        socket.AF_INET,
        socket.SOCK_STREAM,
    )[0][4]
    connection.connect(address)
    client.client_handshake(connection)
    ws = client.websocket(connection)
    client.login(ws, password)
    version = tuple(client.get_ver(ws))
    ws.ioctl(9, 2)
    return connection, ws, client, version


def interrupt_to_prompt(ws, client):
    """Interrupt the current task and wait for a normal REPL prompt."""
    ws.write(INTERRUPT_COMMAND, client.WEBREPL_FRAME_TXT)
    return read_until(ws, b">>> ")


def execute_lines(
    host,
    password,
    lines,
    port=DEFAULT_PORT,
    client_module=None,
    socket_factory=socket.socket,
    address_resolver=socket.getaddrinfo,
):
    """Execute a fixed caller-supplied diagnostic sequence in one session."""
    connection, ws, client, version = open_session(
        host,
        password,
        port=port,
        client_module=client_module,
        socket_factory=socket_factory,
        address_resolver=address_resolver,
    )
    responses = []
    try:
        responses.append(interrupt_to_prompt(ws, client))
        for line in lines:
            data = line.encode("utf-8") if isinstance(line, str) else bytes(line)
            if b"\r" in data or b"\n" in data:
                raise ValueError("diagnostic lines must not contain line breaks")
            ws.write(data + b"\r\n", client.WEBREPL_FRAME_TXT)
            responses.append(read_until(ws, b">>> "))
        return version, responses
    finally:
        connection.close()


def reset_device(
    host,
    password,
    port=DEFAULT_PORT,
    client_module=None,
    socket_factory=socket.socket,
    address_resolver=socket.getaddrinfo,
):
    """Send one hard reset and report whether the old socket closed cleanly."""
    connection, ws, client, version = open_session(
        host,
        password,
        port=port,
        client_module=client_module,
        socket_factory=socket_factory,
        address_resolver=address_resolver,
    )
    try:
        interrupt_to_prompt(ws, client)
        ws.write(RESET_COMMAND, client.WEBREPL_FRAME_TXT)
        disconnect_confirmed = True
        try:
            while connection.recv(256):
                pass
        except TimeoutError:
            disconnect_confirmed = False
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass
        return version, disconnect_confirmed
    finally:
        connection.close()


def main(argv=None, reset_func=reset_device):
    args = build_parser().parse_args(argv)
    try:
        password = load_password(args.secret_path)
        version, disconnect_confirmed = reset_func(
            args.host,
            password,
            port=args.port,
        )
    except Exception as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "action": "reset_failed",
                    "error_type": type(error).__name__,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "action": "reset_sent",
                "disconnect_confirmed": disconnect_confirmed,
                "webrepl_version": list(version),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
