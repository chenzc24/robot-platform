# Deploy ESP32 and MaixCam, Verify Non-Motion PING

- Status: ESP32 complete; MaixCam files published, activation awaiting operator
- Source baseline: `adf4af2`; no robot-arm controller deployment
- Branch: `target/deploy-esp32-maixcam-20260903`
- Validation: L1/L2 only; no enable, velocity, jog, or gripper requests

## Scope and ownership

Initial Git state: synchronized `target/arm-measured-feedback`, with only the
user-owned `.vscode/settings.json` modification. Preserve it untouched.

Editable: this plan, `plan/log.md`, deployment evidence documentation,
ignored device backups, ignored deployment staging/configuration and bounded
deployment helpers if needed. Device scope is the ESP32 runtime Python file
set and the MaixCam arm/video project directories. Do not modify runtime source
without first updating this plan. Local configuration may change only for
discovered addresses, staged L2 mode, and the already approved manual gateway
mode (`YOLO_MODE=True`); preserve credentials and bus settings.

Read-only: raw resources, robot-arm controller/LAN2, TCP232 settings, firmware,
ESP32 pin/CAN parameters, motion limits, safety parameters, user settings.

## Procedure

1. Discover the approved LAN targets without entering REPL or sending motion.
2. Confirm identities, currently deployed versions, and process/resource owners.
3. Back up recoverable target files before replacement; retain hashes locally.
4. Deploy the current ESP32 runtime first in `tcp_v3_l2`, with no CAN creation,
   then verify HELLO/PING/STATUS. A CAN-backed final startup may proceed only
   after current stationary/clear-area confirmation and verified safe startup.
5. Stage and verify current MaixCam arm/video sources; preserve the configured
   UART and network settings. Restart only identified project processes through
   their ownership guards. No arm controller write or motion request.
6. Verify application PING and status. Arm-route PING depends on the existing
   controller service; if unavailable, report gateway and downstream separately.
7. Record exact deployed hashes, modes, actual checks, and remaining blockers.

## Recovery

The operator confirmed the stationary/clear-area deployment condition in this
turn. The prior accepted manual engineering settings remain the target: ESP32
600/800 command limits, explicit Enable, and MaixCam `YOLO_MODE=True`. This
deployment does not exercise those motion permissions. MaixCam's old one-use
admission file is not used by current source; UART/address settings are retained.

Initial findings: ESP32 runtime and WebREPL TCP ports are reachable, but the
WebREPL HTTP upgrade timed out before authentication or file access. USB is not
yet present; recovery assistance was requested. MaixCam SSH identity is verified;
the boot `num` app owns resources and both project listeners are stopped. Its arm
and video directories were copied into ignored local backups before replacement.

The pinned upstream WebREPL client was missing locally and has been restored to
the documented commit in ignored `.tools/webrepl`. No firmware was changed.

ESP32: retain pre-write source/configuration; WebREPL recovery first, USB
COM7/BOOT/RST if required. No flash erase or firmware replacement.
MaixCam: keep prior release/configuration; SSH restoration and launcher-owner
restoration through the known guard. Do not kill unidentified resource owners.

## Validation and submission

Run affected local suites, source syntax checks, deployment readback hashes,
bounded application PING/STATUS, `git diff --check`, and final Git status.
No L3/L4 motion test is included. Commit/push sanitized deployment records on
this branch; do not merge `main` or commit secrets/backups/local configuration.

## Actual results

- Operator connected USB; verified COM7 and ESP32-S3 identity. Backed up root
  Python files and preserved credentials. Published/read back eleven files.
- ESP32 L2 handshake passed before switching to the approved CAN-backed v3
  configuration. Final configuration readback matched. Fresh wireless sessions
  returned WELCOME/PONG/STATE, ready/disabled, no error, zero hold remaining.
- No Enable or nonzero motion request. Startup/cleanup can send CAN zero/disable.
- MaixCam seventeen files published and hash-verified; thirteen Python files
  compiled on-device. Existing `num` app still owns camera/UART0. Activation
  and downstream PING await operator exit/stop approval; no owner guard bypass.
- L1: 137 tests passed (ESP32 55, MaixCam 54, protocol 28). L3/L4 not run.
- PC UI credential provisioning and post-reset WebREPL acceptance are not
  established by the successful backup-credential application probe.
- Detailed evidence and hashes: `docs/deployment/2026-09-03-esp32-maixcam.md`
  and `docs/deployment/2026-09-03-device-manifest.json`.
- User `.vscode/settings.json` remains untouched. Runtime source unchanged.
- Commit intent: publish sanitized partial-deployment evidence on this branch;
  leave MaixCam activation explicitly pending rather than claiming completion.
