# Robot Arm YOLO Manual Control

YOLO mode is the attended engineering interface for repeatable arm motion. It
does not use an application lease, one-use permission, repeated enable, UI
unlock, or chassis-state dependency. The MaixCam route still serializes commands
and returns `RECEIVED`, `ACCEPTED`, `RUNNING`, and `DONE`/`FAULT`/`UNKNOWN`.

## Deployment

Build the DobotStudio project from the repository root:

```powershell
python tools/robot_arm/build_dobotstudio_project.py --output build/robot-arm-yolo --yolo
```

Import `build/robot-arm-yolo` through DobotStudio on LAN2 and start its
`main.py`. On MaixCam, copy `arm_service_config_example.py` to the ignored local
`arm_service_config.py`, set `YOLO_MODE = True`, deploy the arm service sources
over SSH/SCP, and restart the arm service. LAN2 may then be disconnected.

Verify without motion:

```powershell
.\robot arm check --json
```

The downstream status must contain:

```text
service_state=ready;motion_enabled=1;control_mode=yolo
```

## CLI

Signed joint-relative jog, defaulting to a 2-degree step when `--delta` is
omitted:

```powershell
.\robot arm jog-joint --joint 1 --delta 2 --speed 5 --accel 5 --json
.\robot arm jog-joint --joint 1 --delta -2 --speed 5 --accel 5 --json
```

Signed user-coordinate translation, defaulting to 5 mm:

```powershell
.\robot arm jog-xyz --axis x --delta 5 --json
.\robot arm jog-xyz --axis z --delta -5 --json
```

## Python API

```python
from maixcam_arm_client import MaixCamArmClient, open_connection

connection = open_connection("<maixcam-host>", 8780)
client = MaixCamArmClient(connection, "engineering-script")
client.jog_joint((2, 0, 0, 0, 0, 0), accel_pct=5, speed_pct=5)
client.jog_xyz((0, 0, 5), user=0, tool=0, accel_pct=5, speed_pct=5)
```

Each call is a complete relative primitive. Calls may be repeated after the
previous terminal response. The client never retries a state-changing request
whose outcome is unknown.

## UI

Select Hardware, connect the arm route, and wait for YOLO status. The J1-J6 jog
tab defaults to 2 degrees, and the XYZ jog tab defaults to 5 mm. Speed and
acceleration default to 5% and can be set from 1% to 100%. Absolute joint,
absolute Cartesian, and gripper commands use the same route.

The computer application does not alter controller limits, collision settings,
user/tool calibration, or emergency-stop behavior.
