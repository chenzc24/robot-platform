# Magician E6 RPA2 Runtime Project

The maintained source is modular: `main.py`, `arm_motion_service.py`, `motion_link.py`, and `var.py`. The observed DobotStudio workflow accepts only `main.py` and `var.py`, so do not import the modular source directly. Build the controller project from the repository root:

```powershell
python tools/robot_arm/build_dobotstudio_project.py --output tmp/robot-arm-rpa2-l2-two-file
```

Import the resulting project directory as a separate controller project. It contains two code files (`main.py` and `var.py`) plus required import metadata (`prj.json` and an empty `point.json`). The generated `main.py` inlines the reviewed protocol and service code; `var.py` remains a visible local policy file. Its committed defaults answer only `PING` and `STATUS`; all motion is rejected because `MOTION_ENABLED = False` and all reviewed bounds are empty.

The resource-backed project confirms `TCPCreate`, `TCPStart`, `TCPRead`, `TCPWrite`, and `MovJ`. The remaining adapter names are retained as documented controller APIs but require L2/L3 confirmation before claiming their return semantics. `DONE` means only that the selected controller API returned without the service observing an error. It does not mean measured terminal pose, gripper closure, or physical task success. Network cancellation is explicitly unsupported.

For the single supervised console L3 test only, build a separate temporary
project with `--l3-j1-cycle`. It keeps generic `MOVEJ`, `MOVEL`, and `GRIPPER`
disabled and exposes exactly one controller-consumed action: relative J1 `+1°`,
one-second wait, then `-1°`, at 5% speed and acceleration. Do not use this
option outside a current, on-site L3 gate; after the terminal result, return to
the ordinary default-deny project.
