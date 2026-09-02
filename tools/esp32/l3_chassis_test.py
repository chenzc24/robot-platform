"""Run one explicitly attended, bounded ESP32 chassis L3 wheel-rotation test."""

import argparse
import os
import pathlib
import sys
import time


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "protocol"))
sys.path.insert(0, str(ROOT / "src" / "console"))

from chassis_motion_tcp_client import ChassisMotionTcpClient, open_connection


DEFAULT_SPEED_MM_S = 50
DEFAULT_HOLD_MS = 200


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--credential-env", default="ROBOT_CHASSIS_CREDENTIAL")
    parser.add_argument("--client-id", default="l3-attended-test")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--safety-confirmed", action="store_true")
    return parser.parse_args()


def _required(response, response_type):
    if response["type"] != response_type:
        raise RuntimeError("expected_%s" % response_type.lower())
    return response


def execute(arguments):
    credential = os.environ.get(arguments.credential_env)
    if not credential:
        raise RuntimeError("credential_unavailable")

    connection = open_connection(arguments.host, arguments.port, 3.0)
    client = ChassisMotionTcpClient(connection)
    try:
        welcome = _required(client.hello(arguments.client_id, credential), "WELCOME")
        if welcome["payload"]["motion_permitted"] is not True:
            raise RuntimeError("motion_not_permitted_by_device")
        _required(client.enable(), "DONE")
        _required(
            client.velocity(
                DEFAULT_SPEED_MM_S,
                0,
                0,
                DEFAULT_HOLD_MS,
                1000,
            ),
            "DONE",
        )
        time.sleep((DEFAULT_HOLD_MS + 150) / 1000.0)
        state = _required(client.status(), "STATE")["payload"]
        if state["chassis_state"] != "enabled_stopped":
            raise RuntimeError("hold_expiry_did_not_stop")
        _required(client.disable(), "DONE")
        print("L3_RESULT=velocity_hold_expired")
        print("HOLD_STATE=" + state["chassis_state"])
        print("MOTION_PERMITTED=" + str(state["motion_permitted"]))
    finally:
        try:
            connection.close()
        except Exception:
            pass


def main():
    arguments = parse_arguments()
    if not arguments.execute:
        print("DRY_RUN=Use --execute only after the immediate L3 safety gate.")
        return 0
    if not arguments.safety_confirmed:
        raise SystemExit("--safety-confirmed is required with --execute")
    execute(arguments)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
