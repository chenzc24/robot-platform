# Magician E6 RPA2 Runtime Project

This DobotStudio LAN1 project is deployed as `main.py`, `arm_motion_service.py`, `motion_link.py`, and `var.py`. Its committed defaults answer only `PING` and `STATUS`; all motion is rejected because `MOTION_ENABLED=false` and all reviewed bounds are empty.

The resource-backed project confirms `TCPCreate`, `TCPStart`, `TCPRead`, `TCPWrite`, and `MovJ`. The remaining adapter names are retained as documented controller APIs but require L2/L3 confirmation before claiming their return semantics. `DONE` means only that the selected controller API returned without the service observing an error. It does not mean measured terminal pose, gripper closure, or physical task success. Network cancellation is explicitly unsupported.
