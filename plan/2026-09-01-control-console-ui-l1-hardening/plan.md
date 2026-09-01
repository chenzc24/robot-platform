# Control Console L1 Runtime Hardening

- Status: `complete`
- Responsible: `agent`
- Highest validation level: `L1`

## Objective

Strengthen the local Phase B computer-console runtime without adding a local endpoint simulator or contacting hardware. Parse validated ESP32 and MaixCam-arm status payloads into UI state, harden video/session worker failure behavior, and add GUI binding tests that prove decoded frames, persistent faults, and Hardware-mode motion locks.

## Initial state of the workspace

The primary repository is on `target/computer-esp32-tcp-runtime` and has one unrelated, user-owned, unstaged `.vscode/settings.json` change. It remains read-only and unstaged. Work proceeds in the clean isolated worktree `E:\Device Network - control-console-ui-phase-b-hardening`, branched from pushed Phase B commit `83e9a58`.

## Modifiable files

- `src/console/ui/`
- `tests/console/`
- `src/console/README.md`
- `docs/console/control-console-ui.md`
- `plan/2026-09-01-control-console-ui-l1-hardening/plan.md`
- `plan/log.md`

## Read-only files and directories

- `src/console/chassis_motion_tcp_client.py`
- `src/console/maixcam_arm_client.py`
- `protocol/`
- `src/esp32/`, `src/maixcam/`, `src/robot_arm/`, and `tools/`
- `ESP32/`, `Camera/`, and `Robot Arm_Claws/`
- all local configurations, credentials, endpoints, device filesystems, video relays, and hardware

## Shared dependencies

- Direct computer-to-ESP32 RCP/TCP v2 client response shape.
- Computer-to-MaixCam arm client response shape and arm lifecycle semantics.
- Phase B `RuntimeCoordinator`, immutable console state, and default-deny Hardware-mode UI behavior.

## Risk and safety gate

- Risk: malformed or stale status data could be presented as trustworthy; worker shutdown could leave stale visual state; UI wiring could expose motion in Hardware mode.
- Hardware: none. No endpoint, socket, RTSP URL, credential, or device process may be accessed.
- Motion gate: not applicable. State-changing request names remain rejected by the runtime, and Hardware-mode UI buttons remain disabled or rejected.

## Expected work

1. Inspect existing client/protocol response fields and define strict, default-unknown mapping into chassis and arm UI state.
2. Add bounded local tests for malformed status payloads, terminal response shape, queue ordering/closure, and no state-changing dispatch.
3. Harden video worker lifecycle behavior for slow/failed decoding, repeated start/stop, and safe snapshot destinations using injected local fakes only.
4. Add offscreen UI/controller tests for decoded-frame display propagation, retained faults, and hardware-mode motion controls remaining unavailable.
5. Update console documentation with exact L1 scope and residual L2 risk.

## Validation

- `python -m unittest discover -s tests/<suite> -p "test_*.py"` for `console`, `dev`, `esp32`, `maixcam`, `protocol`, and `robot_arm`.
- `QT_QPA_PLATFORM=offscreen python -m ui --smoke-test`.
- `python tools/dev/validate_workspace.py`.
- `git diff --check` and a staged-diff review for secrets, addresses, direct endpoint access, retries, and Hardware-mode motion admission.

L1 uses only fake factories, fake frame containers, temporary local files, and offscreen Qt. No device or real stream is involved.

## Actual results

- Added strict, default-unknown mapping for the complete ESP32 RCP/TCP v2 `STATE` frame and the terminal MaixCam `arm.status` lifecycle response containing the RPA2 arm-service status. Valid state updates lease, motion permission/enabled state, UART/LAN1 reachability, arm-service/controller health, task state, and error display fields. Invalid input keeps the prior state and raises a persistent fault.
- Hardened safe session failure behavior: an exception while handling an allowed query closes that client session, reports the request fault, and never retries it. FIFO ordering and state-changing pre-dispatch rejection remain unchanged.
- Hardened video lifecycle behavior: copied frames remain GUI-thread-owned, frozen display retains its last displayed frame, shutdown reports a timeout as degraded rather than falsely offline, and a completed decoder can start again. The controller no longer advances synthetic video/chassis/arm values in Hardware mode.
- Restricted snapshots to a configured relative subdirectory below the local `logs/` root. Absolute destinations and traversal outside that root are rejected before writing.
- Added local tests for full status mapping, malformed status fault retention, decoded-frame UI binding, Hardware-mode motion locks, decoder failure, blocking stop, repeated start, low frame rate, snapshot write/path failures, connection timeout, half-close failure, FIFO queue ordering, and no state-changing dispatch.
- No local configuration, endpoint, socket, RTSP URL, device process, relay, credential, CAN bus, TCP232, arm controller, or motor was accessed.
- Validation passed: 190 local tests across console (34), development (23), ESP32 (52), MaixCam (44), protocol (28), and robot arm (9); offscreen UI smoke test; workspace validation; source ASCII validation; and `git diff --check`.

## Outstanding matters

- L2 is still required to validate endpoint-specific status fields, socket timeout behavior, video relay behavior, and actual user configuration.
- L3 remains required before any chassis or arm movement request can be admitted.
- End-to-end status freshness, video age, and reconnect policy need real L2 observations before they may be presented as validated runtime behavior.

## Intent to submit

```text
test: harden console runtime state handling
```

Committed and pushed on `target/control-console-ui-phase-b-hardening`; the local branch is synchronized with its upstream.
