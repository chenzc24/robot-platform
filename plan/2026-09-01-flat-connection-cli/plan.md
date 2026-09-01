# Create flat connection management and maintenance of CLI

- Status:`completed`
- Responsible: Agent implemented, user site provided access to mobile hotspots
- Highest validation level:`L2`

## Objective

Without adding backstage daemons, without mixing with deployment and movement control, provide a flat one. `robot` CLI: One layer responsible for ESP32, MaixCam and computer video relays, one layer responsible for the protection of connections and process attribution, one layer responsible for the third stage, stabilization of the error code and recommendations for next steps; and, at the same time, the provision of protected status, logs, stop, restart, force the termination and re-entry of device for subsequent development.

## Initial state of the workspace

```text
## main...origin/main
 M .vscode/settings.json
```

`.vscode/settings.json` is the existing MicroPython button for the user, which keeps this target read-only, does not cover, does not save, does not submit. Current branch synchronizes with remote, the rest of the path is clean.

## Modifyable File

- `robot.cmd`
- `tools/robot_cli.py`
- `tools/dev/connection_manager.py`
- `tests/dev/`
- `.vscode/tasks.json`
- `README.md`
- `docs/development-session.md`
- `docs/runtime-foundation.md`
- `plan/2026-09-01-flat-connection-cli/plan.md`
- `plan/log.md`

## Read-only files and directories

- `.vscode/settings.json`
- `src/esp32/legacy/`
- `ESP32/`, `Camera/`, `Robot Arm_Claws/`
- Local Secret, SSH Configuration, Device Configuration, Cache and Backup
- ESP32 and MaixCam device file system and startup configuration
- TCP232, robot arm, CAN, electrical and chassis control path

## Shared Dependencies

- `protocol/runtime-status.schema.json` structured feedback principles; the CLI default shows only a simplified level III state.
- `tools/maixcam/mediamtx.ps1` The PID and the enforceable documents belong to protection.
- Path to the MaixCam project RTSP process `/root/robot-platform/video/rtsp_server.py` And the PID file.
- ESP32 WebREPL port 8266 is only used for accessibility checks, this target is not posted on the RESL, is not uploaded, is not reset.

## Risk and safety door

- Risk: The wrong process target may interrupt the unrelated program; The device restart may change its operational status; The current reset of the ESP32 program may have initialised CAN and the power.
- Device: ESP32 and MaixCam, execute L2 discovery, port, SSH, RTSP and status read; allow the use of existing start-up scripts when confirming that the project RTSP is not running and ensure computer side media relay.
- User Operations: Maintaining access to the same cell phone hotspot; This round does not require operating BOOT/RST or generating motion.
- Backup and recovery: do not modify the device file or start configuration; MaixCam only initiates the missing video process, which can be stopped and restarted using existing scripts.
- The movement confirmed that the ESP32 restart in .CLI must remain protected from the denial; and that MaixCam will not be ordered to stop, kill or reset.

## Expected work

1. One-time, no back-office process connection manager to support ESP32 detection, maixcam IPv4/SSH/RTSP check, current relay status and single case lock.
2. Achieved `connect/status/details/disconnect/ps/logs/stop/restart/kill/reboot` Command, Level 3, Summary, JSON output, Stable exit code and target attribution protection.
3. With a fake network, a fake process and a false command executioner covering the gill, etc., fuzzy discovery, partially running, ownership mismatch, protecting rejection and command route.
4. Add four daily entrances to VS Code, and retain the existing fine particle scale as an advanced diagnostic.
5. Conduct a read-only L2 status check at the current hotspot; confirm the remote project process and execute the script, etc. `connect`Only the missing MaixCam video service and the computer relay.

## Validation

- New CLI and Connect Manager module testing.
- All protocols, ESP 32 and MaixCam local tests.
- Python without cache compiled, VS Code JSON, official source language, CLI help and JSON output check.
- L2: ESP32 TCP 8266, MaixCam SSH, RTSP port and current process state; Launching missing MaixCam video service and computer trunking review status.
- `git diff --check`
- `git status --short --branch`

L1 covers command routers, process attribution, status aggregation and failure feedback; L2 only validates real connection and missing service start, does not execute remote stop, strong kill, whole machine restarts, uploads, returns or any movement.

## Actual results

- Add root directory `robot.cmd` And two English Python modules that form flat CLI without backstage daemons; the daily command is `connect/status/details/disconnect`,maintenance command as `ps/logs/stop/restart/kill/reboot`.
- Unified display only `maixcam/esp32/camera/video` Four inspections and `READY/DEGRADED/OFFLINE`Level 3 general state; all commands support JSON, exit code to distinguish success, anomaly, misuse and protection refusal.
- ESP32 found that by visible values, successful caches, ARP active candidates and low-and-mode scans were carried out sequentially; after the real hotspot first round and a scan of leaks was sent to 8266, the policy was revised and the ESP32 online was reconfirmed.
- `connect`Only the missing device RTSP and computer relays are activated without repeating the health status; the first real run restores MaixCam RTSP and the current FFmpeg/MediaMTX, and then the other run 3.29 seconds back to READY and `changed=false`.
- The Windows external process output is replaced by a temporary file instead of a capture conduit, repairing FFmpeg/MediaMTX without CLI leaving; real `restart relay` In 6.76 seconds, the subsequent unified status remains READY.
- Process maintenance only accepts fixed targets; MaixCam terminates script validation PID, survival and `/proc/<pid>/cmdline`It's part of it. `--force`and confirm; ESP32 restarts to maintain rejection on the code level.
- A total of 68 tests were passed for L1: 4 for the protocol, ESS32 30, MaixCam 18 and CLI 16; CLI Source No Cache Compiled, VS Code 46 jobs JSON, official source language and Git format checked.
- L2 confirms that ESP32 TCP 8266, MaixCam SSH, Device RTSP, this aircraft is online, and WebRTC;
- The current round does not log in to ESP32 REPL, upload the device source code, resume ESP32, stop/strike MaixCam video, restart the device or create any chassis/robot arm movement.

## Outstanding matters

- MaixCam failed to re-initiate and restart the same internal camera. `num`(b) CLI provides clear feedback and maintains access, but does not automatically kill non-project processes.
- `robot reboot maixcam`And the real MaixCam. `stop/restart/kill`Only command routers, confirmations and fake implementer tests are used, and no destructive acceptances are performed on the real machine.
- `robot reboot esp32`Stay locked, and must be deployed and validated by L3 security door.
- CLI currently manages ESP 32, MaixCam and video; Robot arm-connector adaptor to be added after TCP 232 and LAN1 parameters have been confirmed.

## Experience signal (for manual review)

- Candidate signal: When the Windows parent captures the output, the back-stage media sub-process may inherit the conduit and prevent the one-time CLI from exiting; using a temporary file to take over the external command output avoids waiting for the conduit EOF. This goal is only to record the facts, not create an experience document.

## Intent to submit

```text
feat: add flat robot connection CLI
```
