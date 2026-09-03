# Magician E6 RPA2 Runtime Project

The maintained source is modular: `main.py`, `arm_motion_service.py`, `motion_link.py`, and `var.py`. The observed DobotStudio workflow accepts only `main.py` and `var.py`, so do not import the modular source directly. Build the controller project from the repository root:

```powershell
python tools/robot_arm/build_dobotstudio_project.py --output tmp/robot-arm-rpa2-l2-two-file
```

Import the resulting project directory as a separate controller project. It contains two code files (`main.py` and `var.py`) plus required import metadata (`prj.json` and an empty `point.json`). The generated `main.py` inlines the reviewed protocol and service code; `var.py` remains a visible local policy file. Its committed defaults answer only `PING` and `STATUS`; all motion is rejected because `MOTION_ENABLED = False` and all reviewed bounds are empty.

The E6 4.6.0.3 controller package confirms the controller-resident Python
whitelist exposes `MovJ`, `MovL`, `RelJointMovJ`, `RelMovLUser`, `Wait`,
`CheckMovJ`, `CheckMovL`, `GetAngle`, and `GetPose`. It does not expose the
TCP/IP API names `GetCurrentCommandID` or `RobotMode` to a DobotStudio Python
project. Motion calls therefore follow the
course project model: call the exported `pluginPy` function directly and let a
controller exception signal failure. Do not apply Python truthiness to its
undocumented return object. `DONE` means the sequential controller-Python calls
returned, but still does not prove measured terminal pose, gripper closure, or
physical task success. Network cancellation is explicitly unsupported.

For repeatable attended engineering control, build the YOLO project:

```powershell
python tools/robot_arm/build_dobotstudio_project.py --output build/robot-arm-yolo --yolo
```

This sets `YOLO_MODE = True` in generated `var.py`. It exposes relative J1-J6
and user-coordinate X/Y/Z jogs plus the absolute joint, linear, and gripper
API. It has no one-use grant, application lease, repeated enable, or chassis
dependency. Protocol validation and one-command-at-a-time transport ordering
remain active; native controller limits, collision behavior, and emergency stop
are unchanged.

`STATUS` now samples `GetAngle()` and `GetPose(0, 0)`. The fixed state payload
marks the sample valid only when both calls normalize to six finite values; a
read or shape failure is reported as unavailable without stopping the service.
The actual controller return containers still require one stationary L2 check
before this source is rebuilt and deployed.

Fault-v1 adds bounded structured error evidence, User/Tool-correct XYZ preflight,
CAPS/FAULTS and explicit capability-gated CLEARERR/RECOVER contracts. The current
project does not wire undocumented controller alarm functions: controller query,
clear and verified service recovery remain unsupported. See
[fault management](../../../docs/robot-arm/fault-management.md).

The builder also inlines arm_faults.py. ACK/RUNNING are emitted before native
motion calls; a blocked native call still prevents concurrent status/clear in
this single-threaded project. No cancellation, auto-enable or resume is added.
