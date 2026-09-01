"""Run fixed startup, PS2, and guarded chassis probes through WebREPL."""

import argparse
import json
import pathlib
import sys


TOOLS_DIR = pathlib.Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from webrepl_reset import execute_lines, load_password


STARTUP_LINES = (
    "import __main__",
    "print('PROBE_MAIN', hasattr(__main__, 'chassis'))",
    "print('PROBE_MODE', __import__('robot_config').RUN_MODE)",
    "print('PROBE_RESET_CAUSE', __import__('machine').reset_cause())",
    "hasattr(__main__, 'chassis') and __main__.chassis.disable()",
)

PS2_LINES = (
    "from ps2_lib import PS2Controller",
    "from robot_config import PS2_DI,PS2_DO,PS2_CS,PS2_CLK",
    "p=PS2Controller(di=PS2_DI,do=PS2_DO,cs=PS2_CS,clk=PS2_CLK)",
    "p.init_vibration()",
    "p.update()",
    "print('PROBE_PS2',p.scan[1],p.scan[2],p.data,p.scan[5],p.scan[6],p.scan[7],p.scan[8])",
)

DRIVE_LINE = (
    "exec(\"import time\\nc=__import__('__main__').chassis\\n"
    "try:\\n    c.prepare()\\n    c.drive(vx=0.05,vy=0.0,omega=0.0)"
    "\\n    time.sleep_ms(300)\\nfinally:\\n    try:\\n        c.stop()"
    "\\n    finally:\\n        c.disable()\\nprint('PROBE_DRIVE complete')\")"
)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("probe", choices=("startup", "ps2", "drive"))
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=8266)
    parser.add_argument(
        "--confirm-lifted",
        action="store_true",
        help="confirm the chassis is physically lifted/restrained for the drive probe",
    )
    return parser


def marker_lines(responses):
    """Return only stable probe markers from WebREPL responses."""
    result = []
    for response in responses:
        text = response.decode("utf-8", "replace")
        for line in text.replace("\r", "\n").splitlines():
            line = line.strip()
            if line.startswith("PROBE_"):
                result.append(line)
    return result


def diagnostic_lines(responses):
    """Return exception summaries without echoing commands or credentials."""
    result = []
    for response_index, response in enumerate(responses[1:], start=1):
        text = response.decode("utf-8", "replace")
        for line in text.replace("\r", "\n").splitlines():
            line = line.strip()
            if line.startswith("Traceback") or "Error:" in line or "Exception:" in line:
                result.append({"response_index": response_index, "message": line})
    return result


def main(argv=None, execute_func=execute_lines):
    args = build_parser().parse_args(argv)
    if args.probe == "drive" and not args.confirm_lifted:
        print(
            json.dumps(
                {"ok": False, "error_type": "SafetyConfirmationRequired"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    if args.probe == "startup":
        lines = STARTUP_LINES
    elif args.probe == "ps2":
        lines = STARTUP_LINES + PS2_LINES
    else:
        lines = STARTUP_LINES + (DRIVE_LINE,)
    try:
        password = load_password(
            pathlib.Path(__file__).resolve().parents[2]
            / "src"
            / "esp32"
            / "app"
            / "secrets.py"
        )
        version, responses = execute_func(
            args.host,
            password,
            lines,
            port=args.port,
        )
        markers = marker_lines(responses)
        diagnostics = diagnostic_lines(responses)
    except Exception as error:
        print(
            json.dumps(
                {"ok": False, "error_type": type(error).__name__},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    expected = {
        "startup": "PROBE_MAIN",
        "ps2": "PROBE_PS2",
        "drive": "PROBE_DRIVE",
    }[args.probe]
    complete = any(marker.startswith(expected + " ") for marker in markers)
    print(
        json.dumps(
            {
                "ok": complete,
                "probe": args.probe,
                "markers": markers,
                "diagnostics": diagnostics,
                "webrepl_version": list(version),
            },
            sort_keys=True,
        )
    )
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
