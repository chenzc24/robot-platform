# Unified image-to-drawing PC runner

- Status: `completed`
- Responsible: `agent`
- Highest validation level: `L1`

## Objective

Provide one dry-run-first PC entry point that accepts either an image or an
existing stroke JSON, validates the physical drawing-board mapping, and selects
exactly one of `baseline`, `localized_baseline`, or `advanced` without changing
the shared device deployment or silently falling back.

## Initial state of the workspace

`git status --short --branch` was clean and synchronized before work:

```text
## main...origin/main
```

Recent simulator and provisional GC4653 calibration goals are already committed
on `main`; there are no unrelated dirty paths to preserve.

After implementation began, an independent physical-localized-rehearsal goal
created dirty simulator-only files and its own plan. Those paths are outside
this goal and will not be modified, staged or committed here. Its use of the
stable drawing planner does not overlap this goal's coordinator/image-input
contract.

## Modifyable File

- `app/run_drawing.py`
- `app/README.md`
- `README.md`
- `src/console/drawing/`
- `config/drawing.example.json`
- `config/drawing-control.example.json`
- `docs/console/drawing-control-modes.md`
- `docs/console/strokereview.md`
- `docs/overall-plan.md`
- `tests/app/`
- `tests/console/`
- `plan/2026-09-08-unified-image-drawing-runner/plan.md`
- `plan/log.md`

## Read-only files and directories

- `src/esp32/`, `src/maixcam/`, `src/robot_arm/`, `protocol/`
- `ESP32/`, `Camera/`, `Robot Arm_Claws/`, `tmp/`
- Device filesystems and all real local configuration

## Shared Dependencies

- StrokeReview `POST /api/v1/process` response and normalized canvas contract
- Existing drawing loader, planner, executor and relocation strategies
- Existing ESP32 and MaixCam runtime clients and safety gates
- One-dimensional localization configuration in `config/console.local.json`

## Risk and safety door

- Risk: PC orchestration can eventually submit coordinated chassis and arm
  motion; this goal performs only local L1 validation with injected fakes.
- Hardware: none.
- User operations: none during this goal.
- Backup and recovery: Git is the source of truth; no device or local secret
  configuration is modified.
- Motion gate: real `--execute` remains guarded by job hash, durable log,
  production-ready configuration and explicit attended safety confirmations.
  L3/L4 is not authorized or performed in this goal.

## Expected work

1. Add an immutable image-to-strokes adapter using the local StrokeReview API.
2. Generalize checkpoint orchestration across the three explicit relocation
   strategies, including open-loop Baseline initial offset handling.
3. Add one PC runner with dry-run default, board-size validation and mode-specific
   localization gates.
4. Add focused fake-device/CLI tests and update operator documentation.

## Validation

- `git diff --check`
- `git status --short --branch`
- Python compilation for changed modules
- Focused app/console unit tests
- Full repository L1 test discovery if focused checks pass

The validation covers parsing, no-device dry run, immutable generated artifacts,
mode selection, checkpoint resume and failure gates. It cannot establish camera,
rail, canvas or real-motion accuracy.

## Actual results

- Added `app/run_drawing.py` as the common image/JSON, three-mode, dry-run-first
  PC entry point. Real execution retains exact job hash, durable log,
  production-readiness, attended operator, emergency-stop, clear-area, arm and
  chassis profile gates; image execution adds explicit auto-review acceptance.
- Added immutable loopback StrokeReview ingestion with source/parameter
  manifest, audit and full response artifacts under ignored local output.
- Generalized the checkpoint coordinator to Baseline, Localized Baseline and
  Advanced while preserving the Localized Baseline compatibility wrapper and
  event names. Baseline starts at the reviewed configured offset; localized
  modes start from a fresh measured lock.
- Added exact drawing-board size validation. Uniform legacy JSON scaling is
  possible only through an explicit flag; non-uniform stretching is rejected.
- Added the Baseline initial JSON-axis offset to the example control config and
  preserved compatibility with older local files by defaulting it to zero.
- Python compilation passed. All 385 discovered repository tests passed: app
  13, console 163, development 28, ESP32 76, MaixCam 58, protocol 28 and robot
  arm 19. The 439-stroke sample dry-ran in all three modes with an explicitly
  reported 210-to-150 mm uniform scale.
- `git diff --check` passed. No hardware connection, deployment, runtime service
  action, configuration write or motion occurred.

## Outstanding matters

- Physical AprilTag corner coordinates, JSON-origin rail position and rail scale
  remain intentionally local, non-production-ready calibration inputs.
- Real Baseline distance accuracy and all coordinated L4 behavior remain untested.
- StrokeReview was not running during final validation; HTTP multipart behavior,
  immutable artifacts and error gates were covered with an injected fake
  loopback response rather than a live processing service.

## Experience signal (for manual review)


## Intent to submit

```text
feat(drawing): add unified image-to-drawing runner
```
