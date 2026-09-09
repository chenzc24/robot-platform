# Deploy the d2469eb MaixCam and ESP32 payloads

- Status: complete
- Responsible: joint
- Highest validation level: L2

## Objective

Deploy the MaixCam arm/video and ESP32 runtime payloads from the verified local
`drawing-d2469eb` package. Preserve all real local configuration and secrets,
back up every overwritten path, activate only stopped/default-deny services,
and verify source hashes plus non-motion protocol readiness.

The operator reports that the robot-arm service is suspended. This goal does
not import or start a controller project and sends no arm or chassis motion.

## Initial audit

- `main` is clean and synchronized with `origin/main` at `a13b09c`.
- Package source is `d2469eb`; all device payload source remained unchanged in
  the metadata-only follow-up commit.
- Prior evidence identifies MaixCam Pro through SSH alias `robot-maixcam` and
  ESP32-S3 MicroPython recovery through USB/COM7. Current identities, power,
  ports, process ownership and states must be re-read before writing.

## Editable scope

- new ignored backups under `device-backups/maixcam/20260909-*` and
  `device-backups/esp32/20260909-*`
- new release paths under `/root/robot-platform/releases/` on MaixCam, followed
  by reviewed activation of `/root/robot-platform/arm` and `/video`
- ESP32 flat application files listed in the package manifest; preserved
  `device_config.py` and `secrets.py` are never replaced
- deployment facts in this plan and append-only `plan/log.md`
- dated deployment record/manifest only if actual readback evidence warrants it
- current package/deployment index status where the completed device publication
  makes the previous "not uploaded" wording obsolete

## Read-only scope and dependencies

- robot-arm controller, TCP232 and LAN2
- all product source, tracked configuration templates and older build outputs
- raw-resource archives
- all device-local configuration except restoring its exact backed-up bytes

## Preconditions and recovery

- MaixCam must identify as the documented Pro/riscv64 target; SSH must work.
  Back up active arm/video trees and preserve `arm_service_config.py`. Recovery
  restores the backed-up trees and prior verified process ownership.
- ESP32 must identify as the documented ESP32-S3 MicroPython target. Back up
  every overwritten root file plus `device_config.py`/`secrets.py` metadata.
  Recovery uses USB/COM7 and the fresh backup; no flash erase is authorized.
- Before writes, verify the chassis reports disabled/stopped or otherwise has no
  active motion owner. Any ambiguous identity, state, backup or recovery route
  stops deployment.

## Validation

- L1: package sidecar, manifest/source hashes and applicable local tests
- L2 MaixCam: staged/active readback hashes, syntax without hardware imports,
  process/resource ownership, arm gateway and RTSP status without arm commands
- L2 ESP32: uploaded/readback hashes, restart, authenticated WELCOME/PING/STATUS,
  `chassis_state=disabled`, no ENABLE/VELOCITY
- final `git diff --check` and status audit

## Safety

No motion commands are authorized. Do not send ENABLE, VELOCITY, line-follow,
arm movement or gripper commands. A reset may emit the runtime's zero/disable
safe output but must not request motion. Unknown state-changing outcomes are not
retried automatically.

## Commit intent

Commit and push only factual deployment records after validation.

## Actual results

- MaixCam identity passed as `maixcam-6c7d`, riscv64, Buildroot/Linux 5.10.4.
  Before deployment only the launcher-owned `num` application was present;
  ports 8780 and 8554 were not listening.
- Backed up 32 active arm files and 12 video files to ignored
  `device-backups/maixcam/20260909-pre-d2469eb`, including the real
  `arm_service_config.py`. Staged release
  `/root/robot-platform/releases/20260909-d2469eb`, verified all 15 payload
  hashes and preserved the configuration byte-for-byte.
- Updated the active MaixCam arm/video payload and verified all active hashes.
  The guarded arm wrapper started as observation-time PID 967, gateway PID 979
  became the sole UART0 owner and listened on 8780, and RTSP PID 983 listened on
  8554. PC status reported the camera online. No downstream arm request was sent.
- ESP32 runtime protocol v3 is reachable and authenticated using the preserved
  ignored credential. It reports service `ready`, chassis `disabled`, zero hold
  remaining and no error. No ENABLE, VELOCITY, STOP or configuration request was
  sent.
- COM7 subsequently appeared as a CH340 USB serial adapter. The device identified
  as ESP32_GENERIC_S3-SPIRAM_OCT running MicroPython 1.27. Its startup entered a
  safe prompt and restored WebREPL, establishing both USB recovery and a file
  channel.
- Backed up all 43 ESP32 files to ignored
  `device-backups/esp32/20260909-pre-d2469eb`, including `device_config.py` and
  `secrets.py`. Uploaded the 14 manifest files, compiled them on-device and
  verified every readback hash; configuration and secrets remained byte-identical.
- Reset the ESP32 once. The deployed `main.py` selects the preserved
  `RUNTIME_MODE=tcp_v3_l3` after its application-status prelude even though
  `RUN_MODE=safe_idle`; therefore the listener and CAN-backed composition did
  start. The preserved `L3_MOTION_PERMITTED=True` was not changed. Post-reset
  authenticated status was protocol 3, service `ready`, chassis `disabled`,
  motion permitted, zero hold remaining and no error.
- No ENABLE, VELOCITY, line-follow, arm command or gripper request was sent.
- Final L2 recheck kept MaixCam 8780/8554 listening with UART0 owned, and ESP32
  authenticated status remained `ready/disabled` with COM7 recovery present.
  All 76 ESP32, 58 MaixCam and 28 protocol tests passed (162 total), as did
  `git diff --check`.
