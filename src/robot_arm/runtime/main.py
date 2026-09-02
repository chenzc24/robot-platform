"""DobotStudio entry point for the default-deny LAN1 RPA2 service."""

from arm_motion_service import ArmMotionService, ArmSafetyPolicy, DobotControllerApi
from var import *


def _failed(result):
    return bool(result[0]) if isinstance(result, tuple) and result else bool(result)


def main():
    policy = ArmSafetyPolicy(MOTION_ENABLED, JOINT_MIN_DEG, JOINT_MAX_DEG, POSE_MIN, POSE_MAX,
                             MAX_ACCEL_PCT, MAX_SPEED_PCT, GRIPPER_MIN_MM, GRIPPER_MAX_MM,
                             L3_TEST_ACTION_ENABLED, L3_TEST_J1_STEP_DEG,
                             L3_TEST_ACCEL_PCT, L3_TEST_SPEED_PCT)
    api = DobotControllerApi(CheckMovJ, MovJ, CheckMovL, MovL, SetParallelGripper,
                             RelJointMovJ, Wait)
    service = ArmMotionService(api, policy)
    error, socket_id = TCPCreate(True, LISTEN_IP, LISTEN_PORT)
    if error or _failed(TCPStart(socket_id, 0)):
        raise RuntimeError("tcp_start_failed")
    while True:
        error, data = TCPRead(socket_id)
        if error:
            raise RuntimeError("tcp_read_failed")
        replies, _ = service.feed(data)
        for reply in replies:
            if _failed(TCPWrite(socket_id, reply.decode("ascii"))):
                raise RuntimeError("tcp_write_failed")


main()
