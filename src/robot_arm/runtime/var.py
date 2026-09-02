"""Local Magician E6 RPA2 policy template.

The tracked template is default-deny. The project builder creates a YOLO/manual
engineering variant without altering this source file.
"""

LISTEN_IP = "192.168.5.1"
LISTEN_PORT = 5200

# The generated engineering project sets YOLO_MODE=True. In that mode the
# application accepts repeatable relative and absolute commands; the Dobot
# controller remains responsible for its native limits, collision response,
# emergency stop, and recovery.
YOLO_MODE = False
MOTION_ENABLED = False
JOINT_MIN_DEG = None
JOINT_MAX_DEG = None
POSE_MIN = None
POSE_MAX = None
MAX_ACCEL_PCT = 20
MAX_SPEED_PCT = 20
GRIPPER_MIN_MM = 0
GRIPPER_MAX_MM = 70

# Human-reviewed, non-executable deployment record. Do not invent values.
SAFE_INITIAL_POSE = None
TOOL_FRAME = None
USER_FRAME = None
PAYLOAD_KG = None
GRIPPER_MODEL = None
