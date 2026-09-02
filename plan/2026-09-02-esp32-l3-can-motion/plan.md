# ESP32 L3 CAN and Controlled Chassis Motion

- Status: `completed`
- Responsible: `agent and on-site operator`
- Highest validation level: `L3`

## Objective

Build and validate one bounded, direct computer-to-ESP32 chassis motion path:
RCP/TCP v2 -> authenticated owner/lease -> heartbeat -> safe chassis state
machine -> real ESP32 CAN -> four motor controllers. The first hardware test
will be a single low-speed, time-bounded chassis movement followed by explicit
local stop and disable evidence.

## Initial state

The committed L2 deployment starts the RCP/TCP v2 listener after reset and
uses `NoMotionChassis`. Real CAN, motor enable/disable, heartbeat stop, and
motion remain unimplemented on hardware. The ESP32 is currently online in L2
safe-disabled state. The worktree is clean on this new branch.

## Editable scope

- `src/esp32/app/` only for a reviewed MicroPython CAN factory, L3 runtime
  composition, startup selection, and fail-closed status behavior
- `tests/esp32/` only for regression coverage of the changed composition and
  fault paths using fakes
- `tools/esp32/` only for an explicitly gated, bounded L3 test client that
  performs no device action without its execution flag
- `config/` only for secret-free L3 configuration templates
- `docs/esp32/`, `docs/runtime/`, and `docs/deployment/` only where the
  implementation or deployment procedure changes
- `plan/2026-09-02-esp32-l3-can-motion/plan.md` and `plan/log.md`
- ESP32 filesystem only after a reviewed deployment manifest, backup, recovery
  route, and the explicit L3 safety gate

## Read-only scope

- `ESP32/`, `Camera/`, and `Robot Arm_Claws/` raw-resource archives
- protocol v2 message schema unless a proven L3 requirement requires a
  separately reviewed shared-contract expansion
- console, MaixCam, robot-arm, TCP232, and existing legacy snapshots
- credentials, hotspot settings, device backups, ESP32 firmware image, and
  robot-arm configuration

## Dependencies and risks

- The vendor CAN rate, pins, motor IDs, speed-mode parameter frames, wheel
  directions, and physical mounting must be traced to preserved resource
  evidence before connecting the real bus.
- `CAN.send()` acknowledges only local transmit acceptance; it is not motor
  feedback. L3 must not report commanded velocity as measured movement.
- The first L3 deployment must have an explicit rollback route to the known
  L2 `NoMotionChassis` files over USB.
- The motion service must stop and disable locally on invalid input, disconnect,
  lease expiry, heartbeat expiry, command expiry, socket failure, CAN error,
  and application fault.

## L3 safety gate — required immediately before any motor/CAN test

The on-site operator must explicitly confirm all of the following for the
current test:

1. A person is present and can operate the physical emergency stop.
2. The chassis is raised, restrained, or placed in the agreed clear test area.
3. The area is clear of people, obstacles, cables, and the robot arm.
4. The arm is disabled or in its confirmed safe pose; it will not be commanded.
5. The expected first command, low speed, maximum duration, local stop,
   disable response, and physical emergency-stop response have been explained.

No motion may be sent before this gate is reconfirmed after the L3 deployment.

## Planned sequence

1. Trace CAN facts from local resources and inspect the current L1 safety code.
2. Define the L3 composition and deployment/rollback manifest without changing
   shared protocol semantics unless necessary.
3. Implement with fake-CAN regression tests and run L1 validation.
4. Review exact device files, back up the L2 release, deploy the L3 release,
   and confirm post-reset state is disabled with no motion.
5. Obtain the immediate safety gate above.
6. Validate, one at a time: authenticated connection, wrong-credential reject,
   acquire, enable with zero writes, explicit stop/disable, heartbeat timeout,
   and one agreed low-speed duration-bounded movement.
7. Record only actual observations, restore L2 on failure, review, commit, and
   push.

## Commit intent

```text
feat: add guarded esp32 chassis l3 can runtime
```

## Actual results

- The current L2 release was downloaded through WebREPL into an ignored local
  recovery directory before the L3 files were replaced. Fourteen L3 files were
  uploaded through WebREPL and their device readback hashes matched the local
  release. Credentials and network values remained in ignored local files.
- The normal serial maintenance command could not enter Raw REPL because the
  resident listener restarts immediately after its automatic soft reset.
  WebREPL file transfer worked without interrupting the resident service, but
  its interactive prompt and later maintenance port became unavailable. A
  direct serial interrupt followed by Raw REPL provided the recoverable
  configuration path without firmware flashing.
- With `L3_MOTION_PERMITTED=False`, the real device restarted, created CAN,
  returned an authenticated `ready`/`disabled` state, and reported no error or
  lease. This establishes only local CAN creation and the startup zero/disable
  output; it does not establish motor feedback.
- After an immediate on-site safety confirmation, the motion flag was changed
  through Raw REPL, read back with a matching hash, and the device restarted.
  It again reported `ready`/`disabled`, no error, no lease, and
  `motion_permitted=true` before movement.
- One attended L3 command was sent: forward `50 mm/s` for `200 ms` with the
  chassis raised/restrained. The user observed normal brief wheel rotation.
  The service subsequently reported `disabled`, no active lease, no hold, and
  no fault. The first test tool's final `RELEASE` arrived after its setup lease
  expired and was rejected; the expiration path had already stopped and
  disabled the chassis. The tool was corrected locally to renew a short motion
  lease after motor initialization. No second motion was sent.

## Residual risks and follow-up

- CAN transmission has no controller acknowledgement, wheel-speed feedback,
  bus-off handling, or motor fault telemetry. A successful state only proves
  local command acceptance and the operator's observation.
- The device is presently in the explicitly selected L3 mode. It must not be
  represented as a general production release until the manual console owns a
  heartbeat session, provides hold-to-run control and a fault/status display,
  and is validated in a separate L3 goal.
- MaixCam, robot arm, vision, and coordinated L4 behavior remain outside this
  goal.
