# One-dimensional chassis line-following core

- Status: `completed`
- Responsible: `agent`
- Highest validation level: `L1`

## Objective

Add a small, transport-neutral ESP32 line-following controller that converts
four configurable digital sensor readings into bounded forward/yaw commands,
stops immediately on line loss or a station candidate, confirms a station with
debounce, and exposes explicit `start`, `step`, `stop`, fault-reset, and status
interfaces for a future coordinated task state machine.

## Initial state of the workspace

The primary worktree was intentionally left untouched:

```text
## main...origin/main [behind 5]
 M .vscode/settings.json
 M app/demo.py
 M plan/log.md
?? pelican-bicycle.svg
?? plan/2026-09-03-arm-xyz-singularity-diagnosis/
?? plan/2026-09-03-arm-yz-drawing-review/
?? plan/2026-09-03-video-stream-diagnosis/
```

Those paths are pre-existing user or historical work and do not overlap this
goal. A separate worktree was created from current `origin/main`:

```text
## target/line-following-core...origin/main
```

Remote-only changes affect the StrokeReview application, README, and factual
log; they do not modify the ESP32 chassis runtime or tests used by this goal.

## Modifyable File

- `src/esp32/app/line_following.py`
- `tests/esp32/test_line_following.py`
- `docs/esp32/line-following.md`
- `src/esp32/README.md`
- `plan/2026-09-08-line-following-core/plan.md`
- `plan/log.md` (append-only for this goal)

## Read-only files and directories

- `ESP32/`
- `src/esp32/legacy/`
- `src/esp32/app/chassis_control.py`
- `src/esp32/app/chassis_motion_tcp_service.py`
- `protocol/`
- `src/console/`
- `config/`
- all pre-existing dirty paths in the primary worktree

## Shared Dependencies

- `SafeMecanumChassis.drive(vx, vy, omega)` and `stop()` contracts
- ESP32 safety states `enabled_stopped` and `moving`
- Existing RCP/TCP v3 connection-health and bounded-velocity safety behavior
- One-dimensional rail localization sequence in
  `docs/console/localization-state-machine.md`
- Four legacy digital inputs are evidence only; their actual pin mapping,
  active electrical level, and centered sensor pattern remain unverified
  hardware configuration

## Risk and safety door

- Risk: runtime source for a moving chassis; incorrect sensor polarity or
  steering sign could command the wrong correction if deployed without L3
  calibration.
- Hardware: none for this goal.
- User operations: none.
- Backup and recovery: no device writes; Git branch is the recovery boundary.
- Motion gate: no L3/L4 action is authorized. Real deployment and motion require
  a separate goal, verified wiring/polarity, low limits, on-site supervision,
  clear area, safe arm pose, and physical emergency-stop control.

## Expected work

1. Implement an injected, non-blocking controller with no hardware side effects
   at import time and no internal infinite loop.
2. Add deterministic fake-sensor/fake-chassis tests for steering, station
   debounce, loss, stale stepping, invalid input, and lifecycle behavior.
3. Document integration boundaries and explicitly leave TCP/task wiring and
   pin configuration for later goals.

## Validation

- `git diff --check`
- `git status --short --branch`
- `python -m unittest tests.esp32.test_line_following -v`
- existing ESP32 unit-test suite
- ESP32 Python source checker

This L1 scope verifies control decisions and fail-safe command ordering with
fakes. It does not establish electrical polarity, sensor placement, traction,
control-loop tuning, station geometry, CAN execution, or physical stopping.

## Actual results

- Added a side-effect-free `LineFollowConfig` and `LineFollower` with explicit
  polarity, centered-pattern, steering-sign, direction, speed, debounce, loss,
  and scheduler-gap configuration.
- The lifecycle exposes `start`, one-sample `step`, `stop`, `reset_fault`, and a
  structured snapshot. It never initializes GPIO, sleeps, loops, enables or
  disables motors, or changes the current TCP command contract.
- Centered and correcting samples generate only `vx` and `omega`; `vy` remains
  zero. Line loss and station candidates stop immediately. Sustained line loss,
  stale stepping, invalid sensors, inactive chassis state, and command failures
  latch the local fault state.
- Fourteen targeted tests passed. The complete ESP32 suite passed 69 tests, and
  the ESP32 source checker compiled all 16 current application files.
- `git diff --check` passed. The first validation invocation used a relative
  virtual-environment path absent from the isolated worktree and therefore ran
  no tests; it was rerun successfully with the primary workspace environment.
- No device connection, GPIO/CAN access, deployment, service start, or physical
  motion occurred.

## Outstanding matters

- GPIO construction, secret-free pin/tuning configuration, scheduler/runtime
  integration, TCP task commands, console orchestration, and obstacle sensing
  remain separate goals.
- Active level, centered pattern, steering sign, station geometry, forward and
  reverse behavior, tuning, stop distance, and real sensor freshness require
  attended low-speed hardware validation before deployment.
- Existing CAN status remains commanded rather than measured feedback, so a
  software stop is not proof of physical standstill.

## Experience signal (for manual review)


## Intent to submit

```text
feat(esp32): add bounded line-following core
```
