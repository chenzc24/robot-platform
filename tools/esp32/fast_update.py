"""Incrementally update the production ESP32 runtime over its USB REPL."""

import argparse
import base64
import hashlib
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FILES = (
    (ROOT / "protocol" / "chassis_tcp_v3.py", "chassis_tcp_v3.py"),
    (
        ROOT / "src" / "esp32" / "app" / "chassis_motion_tcp_service.py",
        "chassis_motion_tcp_service.py",
    ),
    (
        ROOT / "src" / "esp32" / "app" / "chassis_runtime_factory.py",
        "chassis_runtime_factory.py",
    ),
)


class UpdateError(RuntimeError):
    pass


class RawRepl:
    def __init__(self, port, baudrate=115200):
        try:
            import serial
        except ImportError as error:
            raise UpdateError("pyserial is required; use the project virtualenv") from error
        self.serial = serial.Serial(port, baudrate, timeout=0.05, write_timeout=5)

    def close(self):
        self.serial.close()

    def _read_until(self, marker, timeout_seconds):
        deadline = time.monotonic() + timeout_seconds
        data = bytearray()
        while time.monotonic() < deadline:
            chunk = self.serial.read(4096)
            if chunk:
                data.extend(chunk)
                if marker in data:
                    return bytes(data)
        raise UpdateError("serial response timeout waiting for %r" % marker)

    def enter(self):
        self.serial.reset_input_buffer()
        deadline = time.monotonic() + 15
        data = b""
        while time.monotonic() < deadline:
            self.serial.write(b"\x03\x03\x02")
            self.serial.flush()
            try:
                data += self._read_until(b">>> ", 1)
                break
            except UpdateError:
                continue
        if b">>> " not in data:
            raise UpdateError("could not interrupt the resident runtime")
        self.serial.write(b"\x01")
        self.serial.flush()
        self._read_until(b"raw REPL; CTRL-B to exit\r\n>", 3)

    def execute(self, source, timeout_seconds=10):
        encoded = source.encode("utf-8")
        for index in range(0, len(encoded), 512):
            self.serial.write(encoded[index:index + 512])
            self.serial.flush()
        self.serial.write(b"\x04")
        self.serial.flush()
        response = self._read_until(b"\x04>", timeout_seconds)
        start = response.find(b"OK")
        if start < 0:
            raise UpdateError("raw REPL did not accept the command")
        stdout_and_error = response[start + 2:-2]
        if b"\x04" not in stdout_and_error:
            raise UpdateError("raw REPL returned an incomplete command result")
        stdout, error = stdout_and_error.split(b"\x04", 1)
        if error:
            raise UpdateError(error.decode("utf-8", "replace").strip())
        return stdout.decode("utf-8", "replace").strip()

    def reset(self):
        source = b"import machine\nmachine.reset()\n"
        self.serial.write(source + b"\x04")
        self.serial.flush()


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _remote_hash(repl, path):
    return repl.execute(
        "import uhashlib,ubinascii\n"
        "print(ubinascii.hexlify(uhashlib.sha256(open(%r,'rb').read()).digest()).decode())\n"
        % path
    ).splitlines()[-1].strip()


def _remote_read(repl, path):
    encoded = repl.execute(
        "import ubinascii\n"
        "print(ubinascii.b2a_base64(open(%r,'rb').read()).decode())\n" % path,
        timeout_seconds=20,
    )
    return base64.b64decode("".join(encoded.splitlines()), validate=True)


def _remote_write(repl, path, data):
    encoded = base64.b64encode(data).decode("ascii")
    repl.execute(
        "import ubinascii\n"
        "f=open(%r,'wb')\n"
        "f.write(ubinascii.a2b_base64(b'%s'))\n"
        "f.close()\n" % (path, encoded),
        timeout_seconds=30,
    )


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--port", default="COM7")
    result.add_argument("--dry-run", action="store_true")
    result.add_argument("--no-reset", action="store_true")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    desired = [(path, remote, path.read_bytes()) for path, remote in FILES]
    if args.dry_run:
        for path, remote, data in desired:
            print("%s <- %s %s" % (remote, path.relative_to(ROOT), _sha256(data)))
        return 0

    repl = None
    backup_dir = None
    try:
        repl = RawRepl(args.port)
        repl.enter()
        identity = repl.execute(
            "import sys,os\nprint(sys.implementation.name)\nprint(os.uname().machine)\n"
        )
        if "micropython" not in identity.lower() or "esp32s3" not in identity.lower():
            raise UpdateError("COM target is not the expected ESP32-S3 MicroPython board")

        changes = []
        for local_path, remote_path, data in desired:
            current_hash = _remote_hash(repl, remote_path)
            desired_hash = _sha256(data)
            if current_hash != desired_hash:
                changes.append((local_path, remote_path, data, current_hash, desired_hash))

        if not changes:
            print("ESP32 runtime already matches the repository; no files written")
            if not args.no_reset:
                repl.reset()
                print("ESP32 reset requested")
            return 0

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = ROOT / "device-backups" / "esp32" / (stamp + "-fast-update")
        backup_dir.mkdir(parents=True, exist_ok=False)
        for _local_path, remote_path, _data, current_hash, _desired_hash in changes:
            previous = _remote_read(repl, remote_path)
            if _sha256(previous) != current_hash:
                raise UpdateError("backup hash changed while reading %s" % remote_path)
            (backup_dir / remote_path).write_bytes(previous)

        for _local_path, remote_path, data, _current_hash, desired_hash in changes:
            _remote_write(repl, remote_path, data)
            if _remote_hash(repl, remote_path) != desired_hash:
                raise UpdateError("readback hash mismatch for %s" % remote_path)
            repl.execute("compile(open(%r).read(),%r,'exec')\n" % (remote_path, remote_path))
            print("updated %s %s" % (remote_path, desired_hash))

        print("rollback backup: %s" % backup_dir)
        if not args.no_reset:
            repl.reset()
            print("ESP32 reset requested")
        return 0
    except (OSError, ValueError, UpdateError) as error:
        print("ERROR: %s" % error, file=sys.stderr)
        if backup_dir is not None:
            print("rollback backup: %s" % backup_dir, file=sys.stderr)
        return 2
    finally:
        if repl is not None:
            repl.close()


if __name__ == "__main__":
    raise SystemExit(main())
