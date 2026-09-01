"""Run one no-motion MaixCam UART ping and emit one JSON result."""

import argparse
import json
import time

from arm_gateway import ArmDiagnosticGateway
from posix_uart import PosixUartTransport


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="/dev/ttyS0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=1.0)
    return parser


def run_probe(transport, timeout_seconds=1.0, clock=None, sleep=None):
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    gateway = ArmDiagnosticGateway(
        transport.write,
        timeout_seconds=timeout_seconds,
        clock=clock,
    )
    sequence = gateway.request_ping()
    while gateway.pending_sequence is not None:
        data = transport.read()
        if data and gateway.feed(data):
            break
        if gateway.poll():
            break
        sleep(0.01)
    result = gateway.snapshot()
    result["sequence"] = sequence
    result["ok"] = result["state"] == "ready"
    return result


def main(argv=None, transport_factory=PosixUartTransport):
    args = build_parser().parse_args(argv)
    transport = None
    try:
        transport = transport_factory(args.device, args.baud)
        result = run_probe(transport, timeout_seconds=args.timeout)
    except Exception as error:
        result = {
            "ok": False,
            "state": "fault",
            "error_code": type(error).__name__,
            "motion_enabled": False,
        }
    finally:
        if transport is not None:
            transport.close()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
