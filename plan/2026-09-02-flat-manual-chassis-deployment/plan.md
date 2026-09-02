# Deploy Flat Manual Chassis Runtime

- Status: `completed`
- Responsible: `agent and on-site operator`
- Highest validation level: `L3`

## Objective

Deploy the committed flat-manual-control ESP32 watchdog revision, restore the
resident TCP service, and prove a post-reset authenticated disabled state before
any optional attended manual jog.

## Initial state of the workspace

```text
## target/control-console-manual-l3...origin/target/control-console-manual-l3
```

The deployment source is committed and synchronized at `76830c0`. The selected
worktree is clean. The primary worktree's user-owned VS Code setting remains
unrelated and untouched.

## Modifyable File

- `plan/2026-09-02-flat-manual-chassis-deployment/plan.md`
- `plan/log.md`
- Ignored `device-backups/esp32/<deployment-timestamp>/`
- Ignored local ESP32 `device_config.py`, limited to reconstructing the currently
  deployed configuration and setting `L3_MAX_HOLD_MS = 500`
- ESP32 filesystem paths explicitly listed in the deployment manifest below
- Local console process lifecycle after ESP32 L2 acceptance

## Read-only files and directories

- Committed source at `76830c0` during upload
- Credentials, hotspot settings, and `secrets.py` except read-only use by the
  existing deployment client
- MaixCam, robot arm, TCP232, raw-resource archives, and taught points
- All ESP32 files outside the declared manifest

## Shared Dependencies

- ESP32 address must be confirmed from the current hotspot rather than assumed
- WebREPL port 8266 is the maintenance path; TCP 8765 is the runtime path
- Prior ignored backup `device-backups/esp32/20260902-l3-predeploy/` is a recovery
  source, but this deployment must create a fresh backup of every overwritten file
- USB/COM7 plus BOOT/RST is the fallback recovery route if WebREPL does not return

## Risk and safety door

- Risk: WebREPL interrupt and reset touch the resident real-CAN runtime. Startup
  sends zero and disable. Incorrect partial deployment can leave the service
  unavailable and require USB recovery.
- Hardware: ESP32-S3 chassis on Wi-Fi/WebREPL; real CAN/motor runtime is present.
- User operations: Keep power stable and remain present for emergency stop and
  USB recovery. No arm command is part of this deployment.
- Backup and recovery: Read back each overwritten file before upload. On failure,
  restore the fresh backup over WebREPL or USB and reset. Do not erase or flash.
- Motion gate: Before interrupt/upload/reset, the operator must confirm a person
  at the physical emergency stop, a clear area, chassis raised/restrained or in the
  agreed safe zone, arm disabled/safe, and that this deployment sends no requested
  velocity. Post-reset acceptance expects `ready`, `disabled`, no lease, and no
  error. Any later jog requires a second immediate confirmation of direction,
  50 mm/s limit, release-to-stop, and failure response.

## Deployment manifest

Overwrite only:

1. `/chassis_motion_tcp_service.py`
2. `/chassis_runtime_factory.py`
3. `/device_config.py` with the existing deployed values preserved except
   `L3_MAX_HOLD_MS = 500`

The first two files come from committed source at `76830c0`. The configuration is
local and ignored. No `main.py`, `boot.py`, network settings, credentials, CAN
pins/rate, speed limits, or motion permission may change.

## Expected work

1. Confirm current IP, power, physical state, and the full L3 safety gate.
2. Run local tests and hash the three intended local files.
3. Read back and archive the current device copies.
4. Upload one file at a time, read back, and compare hashes.
5. Hard reset, wait for runtime recovery, then use TCP 8765 only for HELLO, PING,
   and STATUS. Do not acquire, enable, or send velocity.
6. Restore the local console process only after the disabled-state check passes.

## Validation

- L1 focused ESP32 and console tests before upload
- L2 post-reset authenticated HELLO/PING/STATUS only
- L3 classification because maintenance interruption and reset touch a real-CAN
  resident runtime, even though this deployment sends no velocity command
- Device readback hashes for all overwritten files
- `git diff --check`
- `git status --short --branch`

## Actual results

- The operator confirmed COM7, physical emergency-stop access, a restrained/safe
  chassis area, and a safe robot-arm state for this deployment.
- TCP 8765 and 8266 were reachable, but WebREPL accepted TCP without completing
  its WebSocket handshake. No WebREPL file operation completed.
- `mpremote resume` initially could not enter Raw REPL while background WebREPL
  output was present. Three direct serial interrupts followed by Ctrl-A reached
  the Raw REPL prompt on COM7. No firmware flash or erase was used.
- Fresh pre-deployment copies of all three manifest files were downloaded to the
  ignored `device-backups/esp32/20260902-flat-manual-predeploy/` directory.
- Device configuration comparison confirmed that the only configuration change
  was `L3_MAX_HOLD_MS: 200 -> 500`. Motion permission, speed limits, CAN bus,
  baud rate, and pins were unchanged.
- The service, factory, and local configuration were uploaded and downloaded into
  `device-backups/esp32/20260902-flat-manual-postdeploy/`. All three SHA-256
  readback hashes matched their local deployment sources.
- ESP32 reset completed and TCP 8765 returned. The authenticated non-motion probe
  returned `WELCOME`, `PONG`, and `STATE` with `ready`, `disabled`,
  `motion_permitted=true`, no lease, and `last_error=none`.
- The new console process started from this worktree as PID 36056. The repository
  virtual environment lacked PySide6, so the validated system Python 3.13 runtime
  was used. The failed launcher attempts never connected to a device.
- L1 before upload passed 43 console and 56 ESP32 tests. No velocity, Acquire,
  Enable, CAN-motion request, MaixCam command, or robot-arm command was sent.

## Outstanding matters

- A manual direction jog is not part of deployment acceptance. The current
  confirmation covered deployment/reset only; a jog requires a fresh immediate
  direction-and-stop confirmation.

## Experience signal (for manual review)


## Intent to submit

```text
chore(esp32): record flat manual runtime deployment
```
