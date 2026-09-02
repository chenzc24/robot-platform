"""Local Magician E6 RPA2 policy template.

Copy to the controller project and fill only after a reviewed L3 safety goal.
Leaving any bounds as None keeps all motion disabled.
"""

LISTEN_IP = "192.168.5.1"
LISTEN_PORT = 5200

MOTION_ENABLED = False
JOINT_MIN_DEG = None
JOINT_MAX_DEG = None
POSE_MIN = None
POSE_MAX = None
MAX_ACCEL_PCT = 20
MAX_SPEED_PCT = 20
GRIPPER_MIN_MM = 0
GRIPPER_MAX_MM = 70

# One-use supervised L3 action. It remains false in the committed runtime
# template and is enabled only in the separately reviewed temporary deployment.
L3_TEST_ACTION_ENABLED = False
L3_TEST_J1_STEP_DEG = 1.0
L3_TEST_ACCEL_PCT = 5
L3_TEST_SPEED_PCT = 5

# Human-reviewed, non-executable deployment record. Do not invent values.
SAFE_INITIAL_POSE = None
TOOL_FRAME = None
USER_FRAME = None
PAYLOAD_KG = None
GRIPPER_MODEL = None
