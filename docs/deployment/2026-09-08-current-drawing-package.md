# Current drawing deployment package

Candidate `drawing-20260908-97253c9` freezes clean `main` commit
`97253c9e79149cf4be2b89df1bd0d575d30c5f9a`. The local package is:

```text
E:\Device Network\build\drawing-97253c9
E:\Device Network\build\drawing-97253c9.zip
```

The final ZIP SHA-256 is stored beside the archive in
`drawing-97253c9.zip.sha256`; it is intentionally outside the ZIP to avoid a
self-referential archive hash.

It is prepared and L1-validated only. It has not been uploaded, imported,
started or tested on hardware. The adjacent `manifest.json` identifies every
payload file. Real local configuration and secrets are deliberately absent.

## Package layout

```text
drawing-97253c9/
├── esp32/root/                 14 flat MicroPython runtime files
├── maixcam/arm/                8 arm-gateway files, including flat protocols
├── maixcam/video/              7 RTSP service files
├── robot-arm/DobotStudio/      main.py, var.py, prj.json, point.json
├── device-config-templates/    examples only; never overwrite real config
├── pc-config-templates/        examples only; copy/review as *.local files
├── DEPLOY.md                   this guide
└── manifest.json               payload SHA-256 manifest
```

## Mandatory preservation

- ESP32: back up the root filesystem and preserve the existing verified
  `device_config.py` and `secrets.py`. Neither is in the deploy payload.
- MaixCam: back up `/root/robot-platform/arm` and
  `/root/robot-platform/video`; preserve the reviewed
  `arm/arm_service_config.py`. The package contains no real endpoint config.
- Robot arm: export/preserve the currently working project. Import the package
  as a new project. Its intentionally empty `point.json` must never replace
  another project's taught points.
- PC: preserve ignored `config/*.local.json` and credentials. Templates remain
  `production_ready=false` and contain no secrets.

## Tomorrow's stopped deployment order

1. Record device identity, power, current versions/process owners and recovery
   paths. Keep USB/COM7 and the physical emergency stop available.
2. Import `robot-arm/DobotStudio` through LAN2 as a new project. Verify User0,
   Tool0, load, limits, Home, pen rack and controller Run binding; leave it
   stopped for the initial checks.
3. Stage `maixcam/arm` and `maixcam/video` in a new release directory. Restore
   the backed-up reviewed `arm_service_config.py`, compile without hardware
   imports, verify hashes and resource ownership, then activate the arm gateway
   and video service.
4. Upload the 14 files from `esp32/root` to the flat MicroPython application
   root only after backing it up. First use a reviewed motion-disabled L2
   configuration, reset, and verify WELCOME/PING/STATUS and disabled state.
5. Verify PC → MaixCam → controller PING/STATUS and RTSP decoding without
   motion. Then prepare one explicitly selected PC mode and its local config.
6. Obtain a new attended safety confirmation before separate low-speed L3 arm
   and chassis tests. Run a two-window subset before any complete L4 image job.

Do not run a three-device one-click deployment and do not retry a state-changing
request whose outcome is unknown.

## Mode readiness

- `baseline`: keep line following disabled. Establish drawing-board dimensions,
  User0 JSON origin, starting offset, and verify command-distance sign/scale.
- `localized_baseline`: additionally calibrate the camera, measured AprilTag
  corners, `json_origin_rail_position_mm`, and `json_mm_per_rail_mm`.
- `advanced`: additionally enable and review all ESP32 line-sensor GPIO,
  polarity, steering and station parameters and pass separate L3 validation.

The current GC4653 matrix is a specification-derived starting value and its
distortion vector is still a placeholder. It must not be marked production
ready until physical calibration is accepted.
