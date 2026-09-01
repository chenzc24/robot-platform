# Build the Offline Runtime Integration Candidate

- Status: `completed`
- Date: `2026-09-01`
- Branch: `target/offline-runtime-integration`
- Highest validation level: `L1`

## Goal

Build one locally testable, deployment-ready candidate that preserves the frozen runtime topology: direct computer-to-ESP32 chassis control, and computer-to-MaixCam-to-arm control. Promote only behavior evidenced by the read-only resource code and existing validated branches. Represent site-specific arm policy as explicit empty/default-deny local configuration. Represent missing CAN feedback and unverified robot-arm cancellation/terminal semantics as known capability gaps rather than invented behavior.

## Initial Workspace State

The primary worktree `E:\Device Network` is on `target/computer-esp32-tcp-runtime` with the user-owned `.vscode/settings.json` modification. It is read-only for this goal. This clean isolated worktree starts from `27b7440` on `target/direct-chassis-motion-v2`.

Read-only resource evidence has been inspected without modification:

- `ESP32/CarControlCode.rar` confirms the ESP32 CAN pins, baud rate, motor IDs/directions, speed-mode writes, and mecanum geometry.
- `Camera/code/used/chuankou.py` confirms MaixCam UART0/UART2 devices and the UART2 pin map.
- The Camera arm-communication example confirms the LAN1 TCP server shape and `MovJ` use.
- `Camera/code/used/flask_ali.py` confirms MaixCam can host a computer-facing HTTP process, but it is not adopted as the runtime protocol.
- Existing source branches provide RCP/TCP v2 L1 chassis safety, RPA1 hardware evidence, and an RPA2 L1 arm-service candidate.

## Editable Scope

- `protocol/` shared envelope and arm link contracts, vectors, and codecs.
- `src/console/` direct chassis client extensions and a MaixCam arm-session client.
- `src/esp32/app/` listener, startup composition, local configuration templates, and deployment documentation.
- `src/maixcam/arm/` computer command endpoint, UART adapter, lifecycle/status code, and launcher scripts.
- `src/robot_arm/runtime/` bounded LAN1 RPA2 service and explicit default-deny policy template.
- `config/`, `tests/`, `tools/sim/`, `docs/`, this goal plan, and `plan/log.md`.

## Read-only Scope

- `ESP32/`, `Camera/`, and `Robot Arm_Claws/` raw resources.
- The primary worktree and user-owned `.vscode/settings.json`.
- Device filesystems, device processes, LAN addresses, credentials, TCP232 configuration, taught points, safety configuration, firmware, and all real hardware.

## Frozen Decisions and Shared Dependencies

- Chassis runtime stays `computer → Wi-Fi/TCP → ESP32 → CAN`; MaixCam never routes chassis commands.
- Arm runtime stays `computer → Wi-Fi/NDJSON → MaixCam → UART0 → TCP232 → arm LAN1`.
- ESP32 uses the resource-confirmed CAN model but starts in a non-motion, no-CAN L2 composition.
- Arm project starts with `MOTION_ENABLED=false` and missing joint/pose bounds. These missing values are a deliberate deny policy, not a permissive placeholder.
- RCP/TCP v2 and RPA2 remain independently versioned; RCP1 and RPA1 remain diagnostics only.
- No CAN acknowledgement, physical chassis feedback, arm network cancel API, or arm controller terminal-motion semantics may be claimed until sourced and tested.

## Planned Work

1. Add the computer-to-MaixCam NDJSON envelope, an arm-only endpoint, non-retrying client, lifecycle mapping, and local simulator.
2. Add the bounded RPA2 LAN1 service with `PING`, `STATUS`, `MOVEJ`, `MOVEL`, and `GRIPPER`, using only observed controller entry points plus explicitly marked API assumptions.
3. Add ESP32 v2 one-client listener/startup composition with ignored local credentials and a safe no-CAN L2 mode. Preserve the resource-confirmed CAN composition behind an explicit deployment mode.
4. Promote resource evidence into versioned configuration references without copying raw archives or secrets.
5. Add default-deny arm-policy templates and a capabilities record for missing arm terminal/cancel and CAN feedback semantics.
6. Add protocol vectors, fakes/simulator tests, release manifest templates, deployment steps, and an English acceptance matrix.
7. Run L0/L1 validation only, record factual results, and submit a reviewable branch.

## Risks and Validation Boundaries

- The current branches have overlapping historical designs. Only direct chassis v2 and arm-only RPA2 code may be integrated; the obsolete MaixCam-to-ESP32 route is excluded.
- `MovJ`, TCP server primitives, and UART device names are resource-backed. `CheckMovJ`, `CheckMovL`, `MovL`, `SetParallelGripper`, controller return semantics, and cancellation require documentary evidence or remain declared assumptions/blocked capabilities.
- No test may construct real CAN hardware, bind a device network address, invoke WebREPL/SSH, upload files, or move hardware.
- L1 tests prove framing and fakes only. L2 deployment and L3 motion require separate goals and the on-site safety gate.

## Validation

- L0: changed Markdown and configuration templates are English-only; relative links, JSON, syntax, secret scan, and `git diff --check` pass.
- L1: protocol vectors, console client, MaixCam endpoint/gateway, arm policy/service, ESP32 listener composition, and simulator fault paths pass locally.
- No L2, L3, or L4 activity occurs.

## Actual Result

Built an offline L1 integration candidate without accessing hardware. It adds a strict computer-to-MaixCam Control Envelope v1, RPA2 CRC framing, a one-request/no-retry MaixCam arm gateway, a computer arm client, a deterministic simulator, and a default-deny Magician E6 LAN1 project. It also adds the ESP32 v2 one-client listener and startup composition for `tcp_v2_l2`; that composition uses `NoMotionChassis`, keeps `motion_permitted=false`, and does not construct CAN or motors.

Promoted resource-backed facts into the integration documentation and templates. Arm safety values are retained as explicit `null` fields and cause motion rejection. CAN acknowledgement, measured chassis feedback, measured arm terminal position, and arm network cancellation are recorded as unsupported capabilities rather than implemented claims. Added a deployment-manifest template, UART ownership/restore launcher, vectors, fakes, tests, and machine-day L2/L3 instructions.

L1 validation passed: 172 local tests (28 protocol, 52 ESP32, 44 MaixCam, 9 robot arm, 16 console, and 23 development-tool tests); selected source compilation, JSON parsing, English/link review, secret review, workspace validation, shell syntax, and Git diff-format checks passed.

## Unresolved Items

- The candidate is not deployed and has no L2 evidence for RCP/TCP v2, RPA2, or the computer-to-MaixCam endpoint.
- ESP32 CAN composition and real motor feedback remain excluded. The resource code confirms command writes but does not prove acknowledgement or measured motion.
- Arm local policy remains intentionally empty/default-deny. Safe pose, joint and Cartesian bounds, user/tool frames, payload, gripper model, and validated gripper range require user research and an L3 goal.
- The arm project reports controller-API return only; it cannot claim measured terminal position, gripper closure, object success, or network cancellation.
- Any change that enables motion, creates CAN, changes TCP232, or uploads to a device requires a separate device goal and the appropriate L2/L3 safety gate.

## Commit Intent

```text
feat: build offline runtime integration candidate
```
