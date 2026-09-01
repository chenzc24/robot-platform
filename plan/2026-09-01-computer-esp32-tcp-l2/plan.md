# Establish the Computer-ESP32 TCP Runtime Link

- Status: `completed`
- Date: `2026-09-01`
- Branch: `target/computer-esp32-tcp-runtime`
- Highest validation level: `L3` because entering WebREPL and resetting the currently deployed legacy PS2/CAN program can initialize motion hardware, even though this goal's TCP protocol is non-motion

## Goal

Apply the user-confirmed runtime boundary change from computer → MaixCam → ESP32 to computer → Wi-Fi/TCP → ESP32 for chassis control. Implement and prove a bounded, non-motion TCP runtime foundation between the computer and ESP32 using one versioned newline-delimited JSON contract, one server owner, explicit sequence matching, timeouts, and safe status. Keep WebREPL strictly as the deployment channel.

This goal ends after real `HELLO/WELCOME`, `PING/PONG`, and `STATUS/STATE` exchanges prove the application link. Motor enable, velocity, CAN integration, runtime authentication, resident startup, and real motion remain a separate L3 goal.

## User Confirmation

The user explicitly confirmed that the computer will control ESP32 directly over Wi-Fi/TCP and MaixCam will no longer route chassis commands. MaixCam remains the video source and robot-arm gateway.

## Initial Workspace State

```text
## main...origin/main
 M .vscode/settings.json
```

`main` was synchronized with `origin/main` before creating this branch. `.vscode/settings.json` is an unrelated user-owned change and remains read-only, unstaged, and uncommitted.

The superseded UART diagnostic is preserved on `target/maixcam-esp32-uart-l2` and is not merged into this branch.

## Editable Scope

- `AGENTS.md`
- `README.md`
- `docs/overall-plan.md`
- `docs/runtime/README.md`
- `docs/network/README.md`
- `docs/deployment/README.md`
- `docs/esp32/chassis-tcp.md` and directly relevant ESP32 status links
- Directly related stale boundary statements in `docs/runtime-foundation.md` and MaixCam development/video status documents
- `src/maixcam/README.md` boundary status only
- `protocol/chassis-tcp-v1.md`, its golden vectors, and a canonical MicroPython-compatible codec
- `src/esp32/app/` files required for the isolated non-motion TCP responder/probe
- `src/console/` files required for the computer non-motion TCP client/probe
- Directly corresponding tests under `tests/protocol/`, `tests/esp32/`, and `tests/console/`
- `tools/dev/validate_workspace.py` to include formal computer-side source in the existing source-language audit
- This goal plan and `plan/log.md`

## Read-only Scope

- `.vscode/settings.json`
- Existing chassis motion, MotorBus, CAN, PS2, control-lease, and safe application entry implementations unless the plan is explicitly expanded for a later motion goal
- Existing MaixCam video and arm implementations
- Robot-arm source, TCP232 configuration, taught points, and all arm networks
- Raw-resource directories, device backups, local secrets, and device filesystems until the hardware gate is satisfied

## Shared Dependencies

- Runtime chassis path becomes computer → trusted LAN → ESP32 TCP service → local safety/CAN.
- Runtime arm path remains computer → MaixCam → UART0/TCP232 → robot arm LAN1.
- Video remains MaixCam → computer.
- ESP32 maintenance remains computer → WebREPL or USB and must never be confused with the runtime TCP service.
- The first TCP service is non-motion and must not import CAN, `MotorBus`, `SafeMecanumChassis`, or legacy PS2 code.
- TCP integrity removes the need for an application CRC, but framing, field bounds, maximum message size, sequence matching, and timeouts remain mandatory.

## Planned Work

1. Update the confirmed runtime and deployment boundaries in the repository entry points and architecture documents.
2. Define `RCP1/TCP v1` as bounded newline-delimited ASCII JSON with `version`, `sequence`, `type`, `ttl_ms`, and `payload`.
3. Implement a canonical MicroPython-compatible codec and stream decoder with golden vectors.
4. Implement an injected ESP32 single-client responder supporting only `HELLO`, `PING`, and `STATUS`; always report `motion_enabled=false`.
5. Implement a bounded ESP32 TCP probe that binds the configured runtime port without initializing motion hardware.
6. Implement a computer client that connects once, performs the three exchanges, validates response type/sequence/state, and closes without automatic retry.
7. Test fragmentation, combined frames, oversized input, invalid JSON/schema, duplicate sequence, wrong direction, timeout, disconnect, and single-owner behavior.
8. After L0/L1 passes, stop for a fresh L3 safety confirmation before WebREPL entry, upload, reset, or real-device validation.

## Safety and Failure Rules

- No motion, enable, disable, stop, velocity, wheel, CAN, or MotorBus message exists in this version.
- The ESP32 server always reports `service=safe_idle` and `motion_enabled=false`.
- Only one client may own the bounded probe; additional clients are rejected or left unserved.
- Invalid, oversized, expired, duplicate-conflicting, or wrong-direction messages never complete a request.
- No automatic request retry. A successful TCP write is not success; only a matching valid response is success.
- The server and computer client use bounded accept, read, and total probe deadlines.
- Do not replace `main.py`, `boot.py`, device configuration, or legacy chassis files during L2 proof.

## Validation

- L0: architecture consistency, JSON, documentation links, English-only source/docs, secret scan, `git diff --check`, and workspace status.
- L1: protocol vectors, ESP32 responder/server fakes, computer client loopback, syntax checks, and all existing regressions.
- L3 gate before hardware: on-site person, physical emergency stop, clear area, raised/restrained chassis, arm excluded, expected zero-motion result, and failure response reconfirmed.
- Hardware after the gate: inspect current device identity and port owner, back up same-name targets, deploy isolated non-startup files, run one bounded server and one client probe, confirm matching sequences and `motion_enabled=false`, then restore the known device state.

## Actual Result

- The confirmed architecture boundary is reflected in the repository entry points and active runtime, network, deployment, ESP32, and MaixCam documents.
- RCP1/TCP v1, its canonical codec, golden vectors, isolated ESP32 responder/probe, and computer client/probe are implemented locally.
- The new protocol deliberately exposes only `HELLO`, `PING`, and `STATUS`; every status reports `motion_enabled=false`, and the ESP32 probe imports no motion implementation.
- L0 passed: JSON validation, Markdown relative-link validation, English-only changed-scope review, secret review, Python syntax checks, workspace validation, and `git diff --check`.
- L1 passed: 16 protocol tests, 39 ESP32 tests, 6 console tests, 23 development-tool tests, 40 MaixCam tests, and 7 robot-arm tests; 131 tests total.
- After the user confirmed the current L3 safety gate, the existing legacy chassis instance was interrupted and disabled through the protected WebREPL startup probe. The device identified MicroPython WebREPL `1.27.0`, the expected legacy `main` chassis object, and `ps2` run mode.
- No same-name target file existed. Exactly `chassis_tcp.py`, `chassis_tcp_service.py`, and `chassis_tcp_probe.py` were uploaded; downloaded copies matched the local source byte-for-byte, and all three modules imported on the device.
- The real computer client completed one exchange with sequences `1,2,3`, responses `WELCOME,PONG,STATE`, `service=safe_idle`, and `motion_enabled=false`. The ESP32 reported client `console`, three handled requests, and `complete=true`.
- No motion, CAN, MotorBus, velocity, enable, or wheel command was sent. The bounded TCP server exited after the exchange.
- A protected device reset was sent afterward. ESP32 WebREPL returned online and the runtime probe port was closed, so no temporary server remained active. The isolated source files remain on the device but are not imported by startup.

## Unresolved Items

- Motion commands, authentication, ownership leasing, heartbeat stop, CAN composition, resident startup, and reconnect recovery remain explicitly deferred to the next L3 goal.
- The reset command was accepted, but the old WebREPL socket did not close before its bounded confirmation timeout. Subsequent port checks confirmed that WebREPL was reachable and the temporary runtime listener was closed; PS2 operation after restoration was not exercised in this goal.

## Commit Intent

```text
feat: add computer esp32 tcp runtime foundation
```
