# MaixCam Source

This directory is the version-controlled source of truth for MaixCam software. The device filesystem is only a deployment target; recover every valid device-side change into this directory.

## Current Status

- OpenSSH diagnostics, SCP deployment, and terminal access are available.
- `app/probe.py` is a non-motion development probe. It does not import `maix` or initialize the camera, UART, GPIO, or robot-arm link.
- `video/rtsp_server.py` is the H.264 RTSP CLI entry point. `video_service.py` owns the injectable backend, camera ownership, lifecycle rollback, and structured status. These modules contain no vision inference, ESP32 control, or arm control.
- `arm/command_service.py`, `arm_motion_gateway.py`, and `arm_command_server.py` implement the L1-only computer-to-MaixCam arm endpoint and RPA2 UART adapter. Their default admission rejects every motion request; UART ownership must be guarded before any deployment.
- Production vision inference and an authenticated/authorized arm-motion deployment remain unfinished. ESP32 chassis communication is no longer a MaixCam responsibility.

See [MaixCam Development](../../docs/maixcam/development.md), [Video](../../docs/maixcam/video.md), and the [Runtime Foundation](../../docs/runtime-foundation.md).
