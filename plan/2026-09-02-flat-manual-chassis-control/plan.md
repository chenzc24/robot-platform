# Flat Manual Chassis Control

- Status: `completed`
- Responsible: `agent, with operator confirmation of the simplified manual-debug behavior`
- Highest validation level: `L1`

## Objective

Replace the protocol-step-heavy chassis debug flow with a flat attended workflow:
connect, start manual control, hold a direction, release to stop, and end manual
control. Correct the timer and rejection semantics that caused a successful jog to
stop and disconnect immediately.

## Initial state of the workspace

```text
## target/control-console-manual-l3...origin/target/control-console-manual-l3
```

The selected control-console worktree is clean. The primary worktree has an
unrelated user-owned `.vscode/settings.json` modification and remains untouched.

## Modifyable File

- `src/console/ui/`
- `src/console/chassis_motion_tcp_client.py`
- `src/esp32/app/chassis_motion_tcp_service.py`
- `src/esp32/app/chassis_runtime_factory.py`
- `config/console.example.json`
- `config/console.local.json` (ignored; timeout fields only)
- `config/esp32-l3-device_config.example.py`
- `tests/console/`
- `tests/esp32/`
- `docs/console/manual-chassis-debug.md`
- `docs/esp32/chassis-tcp.md`
- `docs/overall-plan.md`
- `plan/2026-09-02-flat-manual-chassis-control/plan.md`
- `plan/log.md`

## Read-only files and directories

- `ESP32/`, `Camera/`, and `Robot Arm_Claws/`
- Local ignored credentials and all local configuration fields except the two
  declared console timeout fields
- MaixCam and robot-arm runtime source
- Protocol v1/v2 framing and schemas unless a discovered incompatibility requires
  a documented scope update

## Shared Dependencies

- RCP/TCP v2 ownership and motion command contract
- Existing direct computer-to-ESP32 architecture boundary
- Existing 250..2000 ms lease and 100..500 ms protocol ranges
- Physical emergency stop and the attended L3 gate remain unchanged

## Risk and safety door

- Risk: Changes console control sequencing and the ESP32 response to a velocity
  hold timeout. A hold timeout will stop motion while preserving the enabled
  session; a lease, transport, or local execution failure still stops and disables.
- Hardware: No hardware connection, deployment, or motion in this goal turn.
- User operations: None for L1. A later deployment and jog require a fresh L3
  confirmation.
- Backup and recovery: Git is the source of truth; the currently deployed ESP32
  files are not modified. USB/WebREPL and the prior commit remain the recovery path.
- Motion gate: Not applicable to L1. Before later L3, confirm on-site emergency-stop
  access, clear area, restrained/raised chassis, expected low-speed direction, and
  stop behavior.

## Expected work

1. Separate lease renewal from held-velocity refresh and use compatible defaults:
   500 ms lease renewal, 100 ms velocity refresh, and 500 ms device hold.
2. Make velocity hold expiry stop only; retain stop-and-disable for lease/link/local
   safety failure.
3. Treat explicit device `ERROR` responses as `REJECTED` without disconnecting;
   retain `FAULT`/disconnect for transport or unknown outcomes.
4. Add one-click start/end manual-control operations, keep STOP immediately
   available, prevent duplicate pending starts, and move raw protocol controls to
   an Advanced section.
5. Update focused tests and operator documentation, then run L1 validation.

## Validation

- Focused console and ESP32 unit tests
- Full console and ESP32 test suites if focused checks pass
- Qt offscreen smoke test
- Python syntax compilation for changed source
- `git diff --check`
- `git status --short --branch`

L1 covers sequencing, timeout, queue, explicit rejection, UI enablement, and local
ESP32 state-machine behavior. It does not claim deployment or real-motion success.

## Actual results

- The normal chassis panel now exposes Connect, Start manual control, End manual
  control, direction hold, and STOP. Raw protocol controls remain in Advanced.
- Start automates Acquire and Enable after confirmed status. End sequences STOP,
  Disable, and Release. Pending transitions reject duplicate operator clicks.
- Lease renewal and velocity refresh use separate timers. The local and example
  settings use a 500 ms heartbeat and 500 ms hold; held velocity refresh is
  derived at 100 ms for that hold.
- ESP32 velocity-hold expiry stops and remains `enabled_stopped` with the lease
  intact. Lease expiry and link/execution failure still stop and disable.
- Explicit device rejection is now `REJECTED` without a fault or disconnect;
  transport ambiguity during state change remains `UNKNOWN` and disconnects.
- L1 passed: 203 tests (43 console, 56 ESP32, 28 protocol, 44 MaixCam,
  23 development, 9 robot arm), offscreen Qt smoke, Python compilation,
  workspace validation, and `git diff --check`.
- No device connection, deployment, reset, CAN output, or motion occurred.

## Outstanding matters

- ESP32 deployment and an attended L3 jog remain a separate post-commit action.
  The ignored ESP32 device configuration must set `L3_MAX_HOLD_MS = 500` when
  this source revision is deployed; the committed example already reflects it.

## Experience signal (for manual review)

The repeated immediate-stop failure exposed an invalid timer relationship and a
conflation of command rejection with transport failure.

## Intent to submit

```text
refactor(console): flatten attended chassis control
```
