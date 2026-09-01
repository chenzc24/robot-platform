# Integrate Direct Chassis Motion over RCP/TCP v2

- Status: `completed`
- Date: `2026-09-01`
- Branch: `target/direct-chassis-motion-v2`
- Highest validation level: `L1`

## Goal

Replace the superseded MaixCam-to-ESP32 UART motion route with a local, testable computer-to-ESP32 TCP motion foundation while preserving MaixCam as the video and robot-arm gateway.

This goal will:

1. Define a new motion-capable RCP/TCP v2 contract without changing the real-device-validated non-motion RCP1/TCP v1 contract.
2. Connect authenticated TCP session, ownership lease, heartbeat, bounded velocity, stop, disable, release, status, duplicate protection, and local watchdog behavior to the existing injected `ControlLease` and `SafeMecanumChassis` interfaces.
3. Add a computer-side client that handles the full response lifecycle without automatic motion retry.
4. Add a computer-side dual-session router that sends chassis commands directly to ESP32 and arm commands to an injected MaixCam arm session.
5. Prove the transport-independent safety behavior with local fakes only.

CAN construction, device startup wiring, deployment, hardware connection, real motion, MaixCam endpoint implementation, and robot-arm deployment are outside this goal.

## Initial Workspace State

The primary worktree `E:\Device Network` is on `target/computer-esp32-tcp-runtime` at the real-device-validated commit `344a428`. It contains an unrelated user-owned `.vscode/settings.json` modification that remains read-only and unstaged.

This goal runs in the isolated clean worktree `E:\Device Network - direct-chassis-motion`, created from exactly `344a428`. The independently pushed `target/motion-services-v1` branch remains read-only and will be used only as a design reference for safety-state behavior and the future arm integration.

## Editable Scope

- `protocol/chassis-tcp-v2.md`
- `protocol/chassis-tcp-v2-vectors.json`
- `protocol/chassis_tcp_v2.py`
- `src/esp32/app/chassis_motion_tcp_service.py`
- `src/console/chassis_motion_tcp_client.py`
- `src/console/motion_router.py`
- Direct corresponding tests under `tests/protocol/`, `tests/esp32/`, and `tests/console/`
- `docs/esp32/chassis-tcp.md`
- `docs/runtime/README.md`
- `src/console/README.md`
- This goal plan and `plan/log.md`

## Read-only Scope

- `.vscode/settings.json` and the complete primary worktree.
- RCP1/TCP v1 codec, vectors, service, probe, client, and tests except for documentation links that describe version coexistence.
- Existing CAN, MotorBus, chassis safety core, control lease, boot, application, and production `main.py` implementations.
- MaixCam video, UART, and robot-arm source.
- The complete `target/motion-services-v1` worktree and branch.
- `ESP32/`, `Camera/`, and `Robot Arm_Claws/` raw resources.
- Device filesystems, configuration, credentials, backups, and local caches.

## Shared Contracts and Decisions

- The production chassis runtime owner is the computer over one dedicated Wi-Fi/TCP connection. MaixCam must not route chassis motion.
- The production arm route remains computer to MaixCam to UART/TCP232 to arm LAN1.
- RCP1/TCP v1 remains the immutable non-motion hardware evidence. Motion uses explicit protocol version 2 and cannot be inferred from a v1 `WELCOME` or `PONG`.
- Authentication uses an injected local credential verifier. No credential is committed, logged, echoed, or stored in status. The first version relies on the controlled WPA-protected LAN and does not claim TLS.
- Ownership is bound to the authenticated TCP session. Only one active owner is allowed.
- ESP32 independently enforces limits, lease expiry, velocity hold expiry, safe stop, and disable. Computer orchestration cannot weaken those checks.
- A disconnected or faulted TCP runtime calls local stop and disable through injected chassis dependencies.
- State-changing requests are never retried automatically after an unknown outcome.
- Cross-device admission remains on the computer, while ESP32 and the arm retain final local admission and safety.

## Planned Work

1. Define exact RCP/TCP v2 JSON fields, command payloads, response payloads, lifecycle, session rules, TTL, duplicate behavior, and golden vectors.
2. Implement a MicroPython-compatible v2 codec without importing sockets, CAN, or motor modules.
3. Implement the ESP32 service with default-deny authentication and motion policy, session ownership, lease heartbeat, bounded velocity, local watchdogs, and fault containment.
4. Implement a resident connection loop abstraction with injected TCP connection and continuous safety polling, but no listener binding or startup integration.
5. Implement the computer client with sequence correlation, lifecycle validation, bounded reads, no automatic retry, and explicit unknown outcomes.
6. Implement the computer dual-session router with strict target/name/payload validation and injected cross-device admission.
7. Add deterministic tests for framing, authentication, lease, hold expiry, duplicate/conflict, disconnect, fault, lifecycle, routing, and no-auto-retry behavior.
8. Update English runtime documentation to show the direct chassis route and arm-only MaixCam role.

## Risks and Boundaries

- No real socket, Wi-Fi session, WebREPL, CAN, motor, MaixCam, TCP232, robot API, or device process is authorized in this goal.
- The injected credential comparison is access control, not a physical safety mechanism and not transport encryption.
- A successful CAN write still cannot prove measured wheel motion or physical stop because the current MotorBus has no acknowledgement.
- The current inherited speed limits exist in software but are not yet accepted as safe real-hardware limits.
- Resident boot integration and real CAN construction remain separate L3 work because the deployed legacy application can initialize motion hardware.
- The generic MaixCam arm endpoint and robot-arm service will be integrated in a later bounded goal from the arm-only portions of `target/motion-services-v1`.

## Validation

- L0: JSON parsing, Markdown links, English/ASCII source checks, secret scan, unsafe-default scan, `git diff --check`, and workspace status.
- L1: protocol vectors and invalid frames; authentication; one-client session; ownership and heartbeat; bounded velocity; hold and lease expiry; stop/disable on disconnect and faults; duplicate replay/conflict; client lifecycle and timeout; direct-chassis versus arm-gateway routing; complete repository regression.
- Confirm the primary worktree and `.vscode/settings.json` remain outside this goal's staging scope.

## Actual Result

- Added an immutable-by-version RCP/TCP v2 contract, canonical MicroPython-compatible codec, and golden vectors. Existing RCP1/TCP v1 files and tests remain unchanged and continue to reject motion types.
- Added an ESP32 service core with an injected default-deny credential verifier, session-bound ownership, `250..2000 ms` lease heartbeat, explicit enable, bounded velocity, stop, disable, release, status, duplicate replay/conflict handling, and local hold/lease watchdogs.
- Added an injected connection runtime that polls watchdogs even when no command arrives. Disconnect, authenticated parse failure, short write, execution failure, lease expiry, and hold expiry all attempt both stop and disable. A failed stop does not skip the disable attempt.
- Added safe session replacement semantics: disconnect clears authentication, ownership, decoder state, cached responses, and sequence state; a faulted service refuses a replacement connection until it is diagnosed and restarted.
- Added a computer client with strict sequence and lifecycle correlation, no sequence wrap within one connection, and `UNKNOWN` outcome semantics for state-changing requests that lose terminal evidence. No automatic retry path exists.
- Added a flat computer router that sends `chassis.*` only to the direct ESP32 session and `arm.*` only to the injected MaixCam arm session. Motion requires an injected cross-device admission callback.
- Updated the English ESP32, runtime, and console documentation to describe v1/v2 separation, direct chassis ownership, arm-only MaixCam routing, and the next L2/L3 gates.
- L1 validation passed: 157 repository tests total, including 26 new v2 protocol, ESP32 service/runtime, computer client, and dual-session router tests. All 73 repository Python files compiled; JSON, workspace, ASCII/source, Markdown-link, secret, unsafe-default, and diff checks passed.
- No device, real socket, Wi-Fi session, WebREPL, CAN, motor, MaixCam process, TCP232, robot API, local credential, configuration, or backup was accessed or modified. No primary-worktree file was modified or staged. The isolated worktree contains only this goal's changes.

## Unresolved Items

- No listener accepts real TCP connections yet. The listener must create or safely reset one service per connection, supply ignored local credential configuration, bound accept/read deadlines, and close behavior.
- RCP/TCP v2 TTL bounds local handling time but cannot independently measure time spent in transit without a shared clock. Sequence ordering, the `100..500 ms` velocity hold, and the `250..2000 ms` lease mitigate stale control; this limitation must be included in L2/L3 evidence.
- The pre-shared credential is not TLS. It is acceptable only on the controlled WPA-protected first-version LAN and is not a physical safety mechanism.
- Production `main.py`, run-mode selection, CAN construction, startup rollback, credential loading, and boot-to-disabled behavior are not wired.
- The MotorBus has no acknowledgement, so `DONE` cannot prove measured motion or physical stop.
- The inherited speed bounds have not been accepted as real-hardware-safe values.
- `DualSessionMotionRouter` is a local routing core, not the persistent computer console endpoint or GUI. The MaixCam arm session remains injected; arm-only source from `target/motion-services-v1` requires a later integration goal.
- No L2 or L3 evidence exists for v2. The next goal must deploy a motion-disabled listener without CAN initialization before any separately authorized L3 motion work.

## Commit Intent

```text
feat: add direct chassis motion tcp v2
```
