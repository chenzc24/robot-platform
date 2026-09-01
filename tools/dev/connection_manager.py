"""Flat connection management for the robot development workspace."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
import ipaddress
import json
import os
import pathlib
import re
import socket
import subprocess
import tempfile
import time


ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / ".device-cache" / "robot-cli"
CACHE_PATH = STATE_DIR / "connection.json"
LOCK_PATH = STATE_DIR / "connection.lock"
MEDIA_WRAPPER = ROOT / "tools" / "maixcam" / "mediamtx.ps1"

DEFAULT_MAIXCAM_HOST = "maixcam-6c7d.local"
DEFAULT_SSH_TARGET = "robot-maixcam"
ESP32_WEBREPL_PORT = 8266
MAIXCAM_RTSP_PORT = 8554
LOCAL_RTSP_PORT = 8555
LOCAL_WEBRTC_PORT = 8889
LOCAL_RELAY_LOG_DIR = ROOT / "logs" / "mediamtx"


@dataclass
class CommandResult:
    """Captured result from one external command."""

    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass
class LinkCheck:
    """One stable connection result exposed to the CLI and future console."""

    name: str
    ok: bool
    code: str
    detail: str
    action: str = ""


@dataclass
class ConnectionReport:
    """Aggregated flat status for the required development links."""

    level: str
    checks: list
    changed: bool = False

    def as_dict(self):
        return {
            "level": self.level,
            "changed": self.changed,
            "checks": [asdict(check) for check in self.checks],
        }


class OperationRefused(RuntimeError):
    """Raised when a protection rule rejects a requested operation."""


class SystemRunner:
    """Run bounded host commands without invoking an intermediate shell."""

    def run(self, args, timeout=10, input_text=None):
        try:
            with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stdout_file:
                with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stderr_file:
                    process = subprocess.Popen(
                        [str(item) for item in args],
                        cwd=ROOT,
                        stdin=(subprocess.PIPE if input_text is not None else subprocess.DEVNULL),
                        stdout=stdout_file,
                        stderr=stderr_file,
                        text=True,
                    )
                    timed_out = False
                    try:
                        if input_text is None:
                            process.wait(timeout=timeout)
                        else:
                            process.communicate(input=input_text, timeout=timeout)
                    except subprocess.TimeoutExpired:
                        timed_out = True
                        process.kill()
                        process.wait(timeout=3)
                    stdout_file.seek(0)
                    stderr_file.seek(0)
                    return CommandResult(
                        124 if timed_out else process.returncode,
                        stdout_file.read().strip(),
                        stderr_file.read().strip(),
                    )
        except OSError as error:
            return CommandResult(127, "", type(error).__name__)


class NetworkProbe:
    """Perform short IPv4-only name and TCP checks."""

    def resolve_ipv4(self, host):
        addresses = socket.getaddrinfo(
            host,
            None,
            socket.AF_INET,
            socket.SOCK_STREAM,
        )
        unique = []
        for item in addresses:
            address = item[4][0]
            if address not in unique:
                unique.append(address)
        if not unique:
            raise OSError("no IPv4 address found")
        return unique[0]

    def tcp_open(self, host, port, timeout=0.35):
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    def local_ipv4_for(self, remote_ipv4):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.connect((remote_ipv4, 9))
            return connection.getsockname()[0]

    def scan_port(self, local_ipv4, port, exclude=()):
        network = ipaddress.ip_network("%s/24" % local_ipv4, strict=False)
        excluded = {str(item) for item in exclude}
        candidates = [
            str(host)
            for host in network.hosts()
            if str(host) not in excluded
        ]

        def check(candidate):
            if self.tcp_open(candidate, port, timeout=0.12):
                return candidate
            return None

        with ThreadPoolExecutor(max_workers=24) as executor:
            return [item for item in executor.map(check, candidates) if item]

    def arp_candidates(self, local_ipv4):
        """Return active same-subnet IPv4 candidates without trusting identities."""
        try:
            result = subprocess.run(
                ["arp", "-a"],
                text=True,
                capture_output=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return []
        network = ipaddress.ip_network("%s/24" % local_ipv4, strict=False)
        candidates = []
        for match in re.findall(r"(?<![0-9.])(?:\d{1,3}\.){3}\d{1,3}(?![0-9.])", result.stdout):
            try:
                address = ipaddress.ip_address(match)
            except ValueError:
                continue
            if address in network and address != network.network_address:
                value = str(address)
                if value not in candidates:
                    candidates.append(value)
        return candidates


class ConnectionLock:
    """Prevent overlapping one-shot connection and maintenance operations."""

    def __init__(self, path=LOCK_PATH):
        self.path = pathlib.Path(path)
        self._handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._handle = self.path.open("a+b")
            self._handle.seek(0)
            if self._handle.read(1) == b"":
                self._handle.write(b"0")
                self._handle.flush()
            self._handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if self._handle is not None:
                self._handle.close()
            self._handle = None
            raise OperationRefused("another robot CLI operation is active") from error
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        if self._handle is None:
            return
        self._handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()
        self._handle = None


class ConnectionManager:
    """Expose flat link state while keeping adapters and protections internal."""

    def __init__(
        self,
        runner=None,
        network=None,
        cache_path=CACHE_PATH,
        maixcam_host=DEFAULT_MAIXCAM_HOST,
        ssh_target=DEFAULT_SSH_TARGET,
    ):
        self.runner = runner or SystemRunner()
        self.network = network or NetworkProbe()
        self.cache_path = pathlib.Path(cache_path)
        self.maixcam_host = maixcam_host
        self.ssh_target = ssh_target

    def _load_cache(self):
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save_cache(self, **values):
        data = self._load_cache()
        data.update(values)
        data["updated_at_unix"] = int(time.time())
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.cache_path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(data, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(self.cache_path)

    def _maixcam_ipv4(self):
        try:
            address = self.network.resolve_ipv4(self.maixcam_host)
            self._save_cache(maixcam_ipv4=address)
            return address, None
        except OSError:
            cached = self._load_cache().get("maixcam_ipv4")
            if cached and self.network.tcp_open(cached, 22):
                return cached, None
            return None, "maixcam_ipv4_unresolved"

    def discover_esp32(self, explicit_host=None, maixcam_ipv4=None):
        candidates = []
        if explicit_host:
            candidates.append(explicit_host)
        cached = self._load_cache().get("esp32_ipv4")
        if cached and cached not in candidates:
            candidates.append(cached)
        for candidate in candidates:
            if self.network.tcp_open(candidate, ESP32_WEBREPL_PORT):
                self._save_cache(esp32_ipv4=candidate)
                return candidate, None

        if not maixcam_ipv4:
            return None, "esp32_address_required"
        try:
            local_ipv4 = self.network.local_ipv4_for(maixcam_ipv4)
            excluded = (local_ipv4, maixcam_ipv4)
            arp_matches = [
                candidate
                for candidate in self.network.arp_candidates(local_ipv4)
                if candidate not in excluded
                and self.network.tcp_open(candidate, ESP32_WEBREPL_PORT)
            ]
            if len(arp_matches) == 1:
                self._save_cache(esp32_ipv4=arp_matches[0])
                return arp_matches[0], None
            if len(arp_matches) > 1:
                return None, "esp32_discovery_ambiguous"
            matches = self.network.scan_port(
                local_ipv4,
                ESP32_WEBREPL_PORT,
                exclude=excluded,
            )
        except OSError:
            return None, "esp32_discovery_failed"
        if len(matches) == 1:
            self._save_cache(esp32_ipv4=matches[0])
            return matches[0], None
        if len(matches) > 1:
            return None, "esp32_discovery_ambiguous"
        return None, "esp32_unreachable"

    def _ssh_check(self):
        return self.runner.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=4",
                self.ssh_target,
                "true",
            ],
            timeout=6,
        )

    def _relay_action(self, action):
        return self.runner.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(MEDIA_WRAPPER),
                "-Action",
                action,
                "-MaixCamHost",
                self.maixcam_host,
            ],
            timeout=20,
        )

    def relay_action(self, action):
        if action not in ("start", "stop", "status"):
            raise ValueError("unsupported relay action")
        return self._relay_action(action)

    def relay_logs(self, lines=80):
        lines = max(1, min(int(lines), 500))
        sections = []
        for name in ("ffmpeg-stderr.log", "stderr.log", "stdout.log"):
            path = LOCAL_RELAY_LOG_DIR / name
            if not path.is_file():
                continue
            content = path.read_text(encoding="utf-8", errors="replace").splitlines()
            sections.append("== %s ==\n%s" % (name, "\n".join(content[-lines:])))
        if not sections:
            return CommandResult(1, "", "no relay logs are available")
        return CommandResult(0, "\n".join(sections), "")

    def _relay_check(self):
        result = self._relay_action("status")
        endpoints_ready = self.network.tcp_open("127.0.0.1", LOCAL_RTSP_PORT)
        endpoints_ready = endpoints_ready and self.network.tcp_open(
            "127.0.0.1",
            LOCAL_WEBRTC_PORT,
        )
        if result.returncode == 0 and endpoints_ready:
            return LinkCheck("video", True, "ok", "local relay ready")
        if result.returncode == 0:
            return LinkCheck(
                "video",
                False,
                "relay_endpoint_unavailable",
                "managed processes are running but local endpoints are unavailable",
                "Run: .\\robot restart relay",
            )
        return LinkCheck(
            "video",
            False,
            "relay_not_running",
            "local video relay is not running",
            "Run: .\\robot connect",
        )

    @staticmethod
    def _level(checks):
        indexed = {check.name: check for check in checks}
        esp_online = indexed.get("esp32") and indexed["esp32"].ok
        maix_online = indexed.get("maixcam") and indexed["maixcam"].ok
        if all(check.ok for check in checks):
            return "READY"
        if esp_online or maix_online:
            return "DEGRADED"
        return "OFFLINE"

    def report(self, explicit_esp32_host=None, ensure_relay=False):
        checks = []
        changed = False
        maixcam_ipv4, maixcam_error = self._maixcam_ipv4()
        ssh_result = self._ssh_check()
        ssh_ready = ssh_result.returncode == 0
        if ssh_ready:
            checks.append(LinkCheck("maixcam", True, "ok", "SSH ready"))
        else:
            checks.append(
                LinkCheck(
                    "maixcam",
                    False,
                    "maixcam_ssh_unreachable",
                    "SSH is unavailable",
                    "Check hotspot membership and the robot-maixcam SSH alias",
                )
            )

        esp32_ipv4, esp32_error = self.discover_esp32(
            explicit_host=explicit_esp32_host,
            maixcam_ipv4=maixcam_ipv4,
        )
        if esp32_ipv4:
            checks.append(LinkCheck("esp32", True, "ok", "WebREPL port ready"))
        else:
            checks.append(
                LinkCheck(
                    "esp32",
                    False,
                    esp32_error or "esp32_unreachable",
                    "WebREPL port is unavailable",
                    "Check the hotspot client list or pass --esp32-host",
                )
            )

        device_rtsp_ready = maixcam_ipv4 and self.network.tcp_open(
            maixcam_ipv4,
            MAIXCAM_RTSP_PORT,
        )
        video_start_failed = False
        if ensure_relay and ssh_ready and maixcam_ipv4 and not device_rtsp_ready:
            start_result = self.remote_video_start()
            if start_result.returncode == 0:
                for _attempt in range(10):
                    if self.network.tcp_open(maixcam_ipv4, MAIXCAM_RTSP_PORT):
                        device_rtsp_ready = True
                        changed = True
                        break
                    time.sleep(0.25)
            if not device_rtsp_ready:
                video_start_failed = True

        if device_rtsp_ready:
            device_video = LinkCheck(
                "camera",
                True,
                "ok",
                "device RTSP ready",
            )
        else:
            error_code = maixcam_error or (
                "maixcam_video_start_failed"
                if video_start_failed
                else "maixcam_rtsp_unavailable"
            )
            device_video = LinkCheck(
                "camera",
                False,
                error_code,
                "device RTSP is unavailable",
                "Exit num or inspect logs, then run: .\\robot connect",
            )
        checks.append(device_video)

        relay = self._relay_check()
        if ensure_relay and device_video.ok and not relay.ok:
            start_result = self._relay_action("start")
            if start_result.returncode == 0:
                changed = True
                relay = self._relay_check()
            else:
                relay = LinkCheck(
                    "video",
                    False,
                    "relay_start_failed",
                    "local relay failed to start",
                    "Run: .\\robot logs relay",
                )
        checks.append(relay)
        return ConnectionReport(self._level(checks), checks, changed=changed)

    def remote_project_processes(self):
        return self.runner.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=4",
                self.ssh_target,
                "ps -eo pid,args | grep '/root/robot-platform/' | grep -v grep || true",
            ],
            timeout=8,
        )

    def remote_video_logs(self, lines=80):
        lines = max(1, min(int(lines), 500))
        return self.runner.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=4",
                self.ssh_target,
                "tail -n %d /root/robot-platform/video/rtsp.log" % lines,
            ],
            timeout=8,
        )

    def remote_video_stop(self, force=False):
        signal_name = "KILL" if force else "TERM"
        script = """set -eu
video_dir=/root/robot-platform/video
pid_file="$video_dir/rtsp.pid"
if ! test -f "$pid_file"; then echo RTSP_NOT_RUNNING; exit 0; fi
pid=$(cat "$pid_file")
case "$pid" in ''|*[!0-9]*) echo RTSP_STOP_REFUSED_INVALID_PID >&2; exit 3;; esac
if ! kill -0 "$pid" 2>/dev/null; then rm -f "$pid_file"; echo RTSP_NOT_RUNNING; exit 0; fi
if ! test -r "/proc/$pid/cmdline" || ! tr '\\000' ' ' <"/proc/$pid/cmdline" | grep -F -q "$video_dir/rtsp_server.py"; then
  echo RTSP_STOP_REFUSED_OWNERSHIP_MISMATCH >&2
  exit 3
fi
kill -%s "$pid"
if test "%s" = TERM; then
  count=0
  while kill -0 "$pid" 2>/dev/null && test "$count" -lt 10; do sleep 1; count=$((count + 1)); done
  if kill -0 "$pid" 2>/dev/null; then echo RTSP_STOP_TIMEOUT >&2; exit 1; fi
fi
rm -f "$pid_file"
echo RTSP_%s pid=$pid
""" % (signal_name, signal_name, "KILLED" if force else "STOPPED")
        return self.runner.run(
            ["ssh", self.ssh_target, "sh", "-s"],
            timeout=15,
            input_text=script,
        )

    def remote_video_start(self):
        return self.runner.run(
            [
                "ssh",
                self.ssh_target,
                "/root/robot-platform/video/start.sh",
            ],
            timeout=40,
        )

    def reboot_maixcam(self):
        return self.runner.run(
            [
                "ssh",
                self.ssh_target,
                "sync; (sleep 1; reboot) >/dev/null 2>&1 &",
            ],
            timeout=8,
        )
