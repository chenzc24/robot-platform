"""Run one computer-to-ESP32 non-motion RCP1/TCP probe."""

import argparse
import json
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
PROTOCOL_DIR = ROOT / "protocol"
if str(PROTOCOL_DIR) not in sys.path:
    sys.path.insert(0, str(PROTOCOL_DIR))

from chassis_tcp_client import ChassisTcpClient, open_connection


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--timeout", type=float, default=3.0)
    return parser


def run(args, connection_factory=open_connection):
    connection = connection_factory(args.host, args.port, args.timeout)
    try:
        return ChassisTcpClient(connection).probe()
    finally:
        connection.close()


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        result = run(args)
    except Exception as error:
        result = {
            "ok": False,
            "state": "fault",
            "motion_enabled": False,
            "error_code": str(error),
        }
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
