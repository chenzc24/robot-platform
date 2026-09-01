"""Inspect or run the guarded MaixCam arm-link probe over SSH."""

import argparse
import json
import pathlib
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
SSH_TARGET = "robot-maixcam"
REMOTE_PROBE = "/root/robot-platform/arm/l2_probe.py"
REMOTE_GUARD = "/root/robot-platform/arm/run_guarded_l2.sh"


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "probe"))
    parser.add_argument("--arm-confirmation", default="")
    return parser


def run_command(command):
    return subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def uart_owner_result(runner):
    result = runner(["ssh", SSH_TARGET, "fuser /dev/ttyS0 2>/dev/null || true"])
    if result.returncode != 0:
        return {"ok": False, "error_code": "ssh_failed", "owner_pids": []}
    pids = []
    for token in result.stdout.split():
        if token.isdigit():
            pids.append(int(token))
    return {
        "ok": True,
        "error_code": None,
        "owner_pids": sorted(set(pids)),
        "uart_available": not pids,
    }


def probe_result(runner, confirmation):
    if confirmation != "ARM_DISABLED":
        return {"ok": False, "error_code": "safety_confirmation_required"}
    result = runner(["ssh", SSH_TARGET, REMOTE_GUARD])
    try:
        payload = json.loads(result.stdout.strip())
    except (TypeError, ValueError):
        return {"ok": False, "error_code": "invalid_probe_output"}
    payload["remote_return_code"] = result.returncode
    payload["ok"] = bool(payload.get("ok")) and result.returncode == 0
    return payload


def main(argv=None, runner=run_command):
    args = build_parser().parse_args(argv)
    if args.action == "status":
        result = uart_owner_result(runner)
    else:
        result = probe_result(runner, args.arm_confirmation)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
