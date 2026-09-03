"""Loopback-only HTTP API and static asset server."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .runtime import WebConsoleError


MAX_BODY_BYTES = 16 * 1024
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/assets/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/assets/overrides.css": ("overrides.css", "text/css; charset=utf-8"),
    "/assets/app.js": ("app.js", "text/javascript; charset=utf-8"),
}


def _handler(runtime, static_root):
    class ConsoleHandler(BaseHTTPRequestHandler):
        server_version = "RobotConsole/1"

        def log_message(self, _format, *_args):
            return

        def _headers(self, status, content_type="application/json; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; frame-src http://127.0.0.1:8889 http://localhost:8889; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")

        def _json(self, status, value):
            body = json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
            self._headers(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _same_origin(self):
            origin = self.headers.get("Origin")
            if not origin:
                return True
            parsed = urlsplit(origin)
            host, port = self.server.server_address
            return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"} and (parsed.port or 80) == port

        def _body(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as error:
                raise WebConsoleError("invalid_content_length", 400) from error
            if length < 0 or length > MAX_BODY_BYTES:
                raise WebConsoleError("request_too_large", 413)
            if length == 0:
                return {}
            try:
                value = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise WebConsoleError("invalid_json", 400) from error
            if not isinstance(value, dict):
                raise WebConsoleError("json_object_required", 400)
            return value

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/api/state":
                self._json(200, {"ok": True, "state": runtime.snapshot()})
                return
            asset = ASSETS.get(path)
            if asset is None:
                self._json(404, {"ok": False, "error": "not_found"})
                return
            filename, content_type = asset
            body = (static_root / filename).read_bytes()
            self._headers(200, content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if not self._same_origin():
                self._json(403, {"ok": False, "error": "origin_rejected"})
                return
            try:
                body = self._body()
                routes = {
                    "/api/chassis/connect": runtime.connect_chassis,
                    "/api/chassis/disconnect": runtime.disconnect_chassis,
                    "/api/chassis/enable": runtime.enable_chassis,
                    "/api/chassis/disable": runtime.disable_chassis,
                    "/api/chassis/stop": lambda: runtime.stop_chassis_motion(reason=body.get("reason") if body.get("reason") in (
                        "pointer_release", "pointer_cancel", "capture_lost", "key_release", "page_blur", "page_hidden",
                        "tab_changed", "input_replaced", "input_failed", "disable", "disconnect",
                    ) else "operator_stop"),
                    "/api/chassis/status": runtime.refresh_chassis_status,
                    "/api/chassis/motion/start": lambda: runtime.start_chassis_motion(body),
                    "/api/chassis/motion/keepalive": lambda: runtime.keep_chassis_motion(body),
                    "/api/arm/connect": runtime.connect_arm,
                    "/api/arm/disconnect": runtime.disconnect_arm,
                    "/api/arm/status": runtime.refresh_arm_status,
                    "/api/arm/diagnostics": runtime.arm_diagnostics,
                    "/api/arm/recovery": lambda: runtime.arm_recovery(body.get("action"), body.get("confirm", False)),
                    "/api/arm/command": lambda: runtime.arm_command(body.get("command"), body.get("payload")),
                    "/api/faults/ack": lambda: runtime.acknowledge_fault(body.get("code")),
                }
                action = routes.get(urlsplit(self.path).path)
                if action is None:
                    raise WebConsoleError("not_found", 404)
                state = action()
                self._json(200, {"ok": True, "state": state})
            except WebConsoleError as error:
                self._json(error.http_status, {"ok": False, "error": error.code, "state": runtime.snapshot()})
            except Exception:
                self._json(500, {"ok": False, "error": "internal_error", "state": runtime.snapshot()})

    return ConsoleHandler


def create_server(runtime, host="127.0.0.1", port=8080, static_root=None):
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("web_console_must_bind_loopback")
    root = Path(static_root) if static_root else Path(__file__).with_name("static")
    return ThreadingHTTPServer((host, port), _handler(runtime, root))
