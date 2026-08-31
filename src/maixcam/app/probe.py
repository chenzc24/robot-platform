"""Report a side-effect-free MaixCam development-channel snapshot."""

import json
import platform
import socket
import sys


def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as source:
            return source.read().strip()
    except OSError:
        return None


def collect_snapshot():
    """Collect identity without importing ``maix`` or opening any device."""
    return {
        "probe": "robot-platform-maixcam",
        "schema_version": 1,
        "hostname": socket.gethostname(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "maixcam_library": _read_text("/maixapp/maixcam_lib.version"),
        "auto_start_app": _read_text("/maixapp/auto_start.txt"),
    }


def main():
    json.dump(collect_snapshot(), sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
