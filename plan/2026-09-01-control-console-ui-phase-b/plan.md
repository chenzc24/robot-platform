# Control Console UI Phase B

- Status: `complete`
- Responsible: `agent`
- Highest validation level: `L1`

## Objective

Add locally tested runtime-adapter foundations to the PySide6 console: ignored local endpoint configuration, one-owner background sessions for the existing direct ESP32 and MaixCam-arm clients, non-blocking result/state propagation, a bounded PyAV RTSP decoder worker, and safe UI integration for hardware connection/status only. All motion remains locked and no real endpoint is contacted.

## Initial state of the workspace

The goal begins in a clean, synchronized Phase A worktree:

```text
## target/control-console-ui-phase-a...origin/target/control-console-ui-phase-a
```

Work continues in the isolated worktree `E:\Device Network - control-console-ui-phase-b` on `target/control-console-ui-phase-b`. The still-running Phase A desktop window, primary worktree, user `.vscode/settings.json`, all device worktrees, local configuration, raw resources, and device filesystems remain outside this goal.

## Modifiable files

- `.gitignore`
- `config/console.example.json`
- `src/console/README.md`
- `src/console/ui/`
- `tests/console/test_control_console_runtime.py`
- `tests/console/test_control_console.py`
- `docs/console/control-console-ui.md`
- `plan/2026-09-01-control-console-ui-phase-b/plan.md`
- `plan/log.md`

## Read-only files and directories

- existing `src/console/chassis_motion_tcp_client.py`
- existing `src/console/maixcam_arm_client.py`
- `protocol/`
- `src/esp32/`, `src/maixcam/`, `src/robot_arm/`
- `tools/`
- `ESP32/`, `Camera/`, and `Robot Arm_Claws/`
- all real endpoint addresses, credentials, device filesystems, media relays, and hardware

## Shared dependencies

- Phase A UI state/controller API and approved UI design.
- RCP/TCP v2 chassis client semantics: one request at a time; state-changing unknown outcomes are never retried.
- MaixCam arm NDJSON client semantics and arm lifecycle states.
- Existing PyAV development dependency and MediaMTX local relay architecture.
- The no-CAN/default-deny ESP32 and arm L1 candidates; neither is deployed.

## Risk and safety gate

- Risk: adapter code could silently use a real endpoint, auto-retry a state-changing command, block the UI, or expose a motion path before L2/L3 validation.
- Hardware: none.
- User operations: none. The currently open Phase A window is not modified or used for hardware testing.
- Backup and recovery: only local source and an ignored template change; no device content exists to back up.
- Motion gate: not applicable. Hardware UI binding admits only connect, ping, status, and disconnect. Lease, enable, velocity, arm motion, and every software stop request stay disabled or rejected in hardware mode.

## Expected work

1. Add secret-free endpoint configuration schema/template and local-file ignore rule.
2. Implement serial background session services that own one client connection, emit connection/result/fault events, enforce one in-flight operation, and never retry a state-changing operation.
3. Implement a bounded RTSP decoder worker that emits copied RGB frames, timestamps, frame rate, and terminal faults, with a cooperative stop path and no inference dependency.
4. Add a runtime coordinator that composes the two session services and video worker from injected factories, enabling local fake-adapter tests without device access.
5. Connect hardware-mode UI to only non-motion connection/status actions when a local configuration is present; preserve the Phase A simulator behavior and all existing locks.
6. Add local adapter, worker, controller, and GUI tests plus documentation.

## Validation

- all six local unittest suites (`console`, `dev`, `esp32`, `maixcam`, `protocol`, `robot_arm`)
- `QT_QPA_PLATFORM=offscreen python -m ui --smoke-test`
- targeted runtime tests with fake socket clients and fake frame decoder only
- `python tools/dev/validate_workspace.py`
- `git diff --check`
- `git status --short --branch`
- review changed source for source ASCII, secrets, hard-coded endpoints, direct real connection calls in tests, automatic retries, and any hardware-mode motion command.

L1 validates local worker behavior and UI wiring only. No config file is created from the template, no process opens a real RTSP URL, and no ESP32, MaixCam, TCP232, arm, CAN bus, or motor is accessed.

## Actual results

- Added an ignored `config/console.local.json` path and a secret-free `console.example.json` template. The template contains no endpoint values or credentials; the chassis credential is referenced only by an environment-variable name.
- Added a local-only runtime coordinator. ESP32 and MaixCam-arm clients are owned by separate FIFO background sessions. They allow only explicit connect, `ping`, `status`, disconnect, and shutdown. State-changing chassis and arm command names are rejected before they reach a client, and no operation retries automatically.
- Added a dedicated PyAV decoder worker that publishes copied RGB `QImage` frames, cooperative stop, terminal fault events, and optional configured snapshots. Tests inject a fake decoder and never import PyAV or access a stream.
- Wired Hardware mode to configuration-gated connection, status, fault, preview, and disconnect events. The GUI continues to disable all lease and motion controls in Hardware mode; controller motion APIs still reject there.
- Added five runtime/controller tests using fake clients and fake frames. The Phase A simulator behavior remains intact.
- No local configuration file was created and no real endpoint, socket, RTSP stream, video relay, device, credential, CAN bus, TCP232, arm controller, or motor was accessed.
- Validation passed: 184 local tests across console (28), development (23), ESP32 (52), MaixCam (44), protocol (28), and robot arm (9); offscreen UI smoke test; workspace validation; source ASCII validation; and `git diff --check`.

## Outstanding matters

- L2 requires a user-authorized local configuration, deployed safe-idle endpoints, and non-motion status checks.
- L3 requires a distinct on-site safety gate before any enable, lease, velocity, or arm action is ever connected through this UI.
- Bounded status polling, heartbeat scheduling, endpoint timeout behavior, and real-video behavior are not validated by this L1 goal.

## Experience signal (for manual review)


## Intent to submit

```text
feat: add console runtime adapter foundation
```

Committed and pushed on `target/control-console-ui-phase-b`; the local branch is synchronized with its upstream.
