# Localized Baseline drawing runner

- Status: `completed`
- Responsible: `agent`
- Highest validation level: `L1`

## Objective

Provide a guarded PC-side `localized_baseline` execution mode that reuses the
deployed device services, executes drawing windows separated by planner
checkpoints, drives the chassis directly without line following, requires a
fresh AprilTag rail lock after every chassis move, applies the measured one-axis
JSON offset, and resumes only from the exact checkpoint.

## Initial state of the workspace

The clean detached worktree at `E:\Device Network-baseline-run` was based on
`origin/main` commit `55a86c6` and was switched to the new branch
`target/localized-baseline`. The primary worktree contains unrelated historical
and user-owned changes and remains untouched.

```text
## HEAD (no branch)
```

## Modifyable File

- `app/localized_baseline_run.py`
- `app/README.md`
- `config/drawing-control.example.json`
- `docs/console/drawing-control-modes.md`
- `docs/overall-plan.md`
- `docs/robot-arm/pc-drawing-task.md`
- `src/console/drawing/`
- `tests/app/test_localized_baseline_run.py`
- `tests/console/test_drawing_control_modes.py`
- `plan/2026-09-08-localized-baseline-runner/plan.md`
- the new factual entry appended to `plan/log.md`

## Read-only files and directories

- `ESP32/`, `Camera/`, `Robot Arm_Claws/`
- deployed device files and generated arm projects
- the primary worktree and its uncommitted files
- `protocol/`, `src/esp32/`, `src/maixcam/`, `src/robot_arm/`
- existing local secret and production configuration

## Shared Dependencies

- RCP/TCP v3 chassis `VELOCITY`, `STOP`, `PING`, and `STATUS` behavior
- MaixCam/RPA2 arm command lifecycle and existing grouped drawing executor
- schema-5 AprilTag rail localization state machine and vision worker
- planner `reposition.required` and `PlanCheckpoint` contract
- existing Baseline and Advanced modes remain explicitly selectable and do not
  silently fall back into one another

## Risk and safety door

- Risk: coordinated arm, chassis, and vision orchestration is L4 when executed;
  a stale localization, unconfirmed stop, or incorrect checkpoint could move
  hardware or corrupt a drawing.
- Hardware: none for this goal; implementation and simulator/unit validation only.
- User operations: none during L1. A later real run requires reviewed local
  configuration and fresh attended L4 confirmation.
- Backup and recovery: no device writes; Git contains the software recovery path.
- Motion gate: no real device connection or motion is authorized by this goal.
  The executable must default to dry-run and require explicit job hash, log path,
  production-ready configuration, and attended safety confirmations.

## Expected work

1. Add `localized_baseline` as a third explicit relocation strategy: direct
   timed chassis motion followed by a fresh AprilTag lock.
2. Add a checkpoint-aware coordinator and guarded PC entry point that executes
   only the arm-safe portion preceding each barrier, relocates, replans with the
   measured offset, and never retries an unknown action.
3. Add deterministic fake-device/state-machine tests and document configuration,
   invocation, stop semantics, and remaining physical calibration requirements.

## Validation

- `git diff --check`
- `git status --short --branch`
- focused app and drawing control/executor tests
- applicable non-GUI console test suite
- dry-run against a representative drawing that requires relocation

L1 proves selection, checkpoint continuity, fresh-generation enforcement,
measured-offset replacement, fail-closed behavior, and lack of device access in
dry-run. It cannot prove physical travel, camera calibration, AprilTag layout,
arm reach, stopping distance, or L4 interlocks.

## Actual results

- Added schema-2 `localized_baseline` while retaining schema-1 Baseline and
  Advanced compatibility. The mode performs refreshed direct motion, attempts
  STOP, validates a complete `enabled_stopped` status, and accepts only a newer
  AprilTag generation; it never invokes line following or uses commanded travel
  as the resumed offset.
- Added a guarded standalone PC runner and checkpoint coordinator. Dry-run loads
  no runtime configuration and opens no devices. Real mode holds one serialized
  ESP32 session with keepalive, obtains an initial lock, reserves each localized
  arm window, returns the pen and homes before chassis motion, and attempts STOP
  plus DISABLE on shutdown.
- `python -m compileall -q app src/console` passed. All 369 discovered app,
  console, protocol, ESP32, MaixCam, robot-arm and development tests passed. The
  focused fake-device scenario completed two arm windows with one direct move
  and a generation-2 to generation-3 AprilTag transition.
- `E:\Downloads\strokes_band.json` dry-ran without device access as five groups,
  439 strokes and 3,903 points with the recorded job hash. Under the safe example
  geometry it fits one window, so physical relocation was not implied.
- `git diff --check` passed. No hardware connection, deployment, service action,
  configuration write, arm/gripper command or chassis movement occurred.

## Outstanding matters

- Real-device L4 validation remains a separate attended goal. Camera intrinsics,
  board coordinates, JSON-origin rail scalar, direction/scale, chassis timing,
  arm safe pose and physical stop behavior remain unvalidated for production.
- The current real sample does not exercise a reposition barrier under the safe
  example geometry; the two-window behavior is L1 fake-device evidence only.

## Experience signal (for manual review)


## Intent to submit

```text
feat(drawing): add localized baseline runner
```
