# Baseline drawing deployment candidate

Candidate `baseline-20260908-301320c` freezes the latest merged `main` commit
`301320c9f1338f5cb12374466f133a1dcc431252`. It is prepared locally but has not
been uploaded, imported, started or tested on hardware. Exact SHA-256 values are
in the [candidate manifest](2026-09-08-baseline-candidate.json).

## ESP32-S3

Deploy the 14 manifest entries from `protocol/chassis_tcp_v3.py` and
`src/esp32/app/` into the existing flat MicroPython application layout. The
ignored `device_config.py` and `secrets.py` must be preserved from a verified
backup and reviewed before replacement.

For Baseline, local configuration must retain the reviewed `tcp_v3_l3` CAN and
motion limits while setting `LINE_FOLLOW_ENABLED = False`. PC relocation uses
the ordinary `VELOCITY` refresh and `STOP` commands; it does not call the
optional sensor follower. Upload first in motion-disabled L2 form, verify
readback hashes and handshake, then use a separate attended gate before an L3
enable or velocity request.

## MaixCam

The manifest freezes the computer command envelope, RPA2 motion link, eight arm
gateway files, and seven video-service files. Stage them in a new release
directory, preserve the ignored `arm_service_config.py`, verify camera and
UART0 ownership, compile on-device without importing hardware modules, and only
then switch the existing arm/video launchers.

Baseline does not consume AprilTag detections. MaixCam is still required for
the PC-to-arm endpoint and may provide the UI video stream. Its local arm config
must match the generated controller project with `YOLO_MODE = True`.

## Robot arm

The existing deterministic builder produced the ignored directory
`build/baseline-301320c-arm-yolo` with:

```text
main.py   700dc58d9cb2dcf97762f59b8a3c346d7fd2f4c140b9378c06323e55692dc8b4
var.py    d7a1f40f680429fc165d33b63d011f428054c557f7c4d36d5ff2bd0b6ed6f6bb
prj.json  c95b07f45676116ab8ac1a45cf2fc50c2e471e0c917e6affcdf2d809a0d67527
point.json 37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570
```

Import the whole generated directory as a new DobotStudio project through
LAN2. Its empty `point.json` must not overwrite another project's taught
points. Preserve/export the currently working project first, verify User/Tool,
load, limits and Run-button binding, and leave the new project stopped for the
initial non-motion PING/STATUS check through MaixCam.

## PC Baseline boundary

There are currently two distinct runnable/tested layers:

- `app/demo.py` is the attended, single-canvas arm-only drawing path previously
  used for the four-stroke demonstration. The merged default remains 15% draw,
  5% travel and 5% acceleration. A dirty primary-worktree edit changes only the
  draw default to 60%; it is not part of this candidate and is not authorized by
  the earlier low-speed acceptance.
- `src/console/drawing/control_modes.py` provides the Baseline chassis
  relocation strategy and planner checkpoint adapter. It is L1 tested but is
  not yet connected to a full grouped arm/chassis executor or a UI task button.

Therefore this candidate can prepare and independently validate the existing
arm drawing path and the direct chassis relocation path. It cannot yet claim a
single-command, 439-stroke, multi-pen, multi-window Baseline run. That requires
the planned guarded PC arm executor/orchestrator connection before L4.

## Deployment and test order

1. Record identities, power state, active versions/configuration and recovery
   paths; back up all three execution targets.
2. Build and compare the candidate against this manifest without exposing local
   secrets.
3. Import the generated arm project as a separate stopped project.
4. Stage ESP32 in motion-disabled L2 mode; hash-readback, reset, then verify
   authenticated PING/STATUS and disabled state.
5. Stage MaixCam into a new release directory; verify hashes, resource ownership,
   arm PING/STATUS and video without motion.
6. Only after a new on-site safety confirmation, test the arm and chassis as
   separate low-speed L3 actions. Do not begin with a coordinated full drawing.
7. Add the missing guarded executor connection and run a two-window subset
   before treating Baseline as an L4 drawing mode.

No automatic retry is permitted for a state-changing request with an unknown
outcome. A software STOP or closed socket is not the physical emergency stop.
