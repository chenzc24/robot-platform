# GC4653 specification-derived camera intrinsics

- Status: `completed`
- Responsible: `agent`
- Highest validation level: `L1`

## Objective

Make the provisional GC4653 camera model traceable to the supplied first-column
native resolution and field of view, retain safe non-production status, and
document why the nominal 5% lens distortion cannot populate OpenCV distortion
coefficients without image calibration.

## Initial state of the workspace

```text
## main...origin/main
```

The primary worktree is clean and synchronized at `7da29e1`. There are no
registered auxiliary worktrees or branches.

## Modifyable File

- `config/camera-calibration.example.json`
- ignored `config/camera-calibration.local.json`
- `docs/console/apriltag-localization.md`
- `tests/console/test_apriltag_vision.py`
- `plan/2026-09-08-gc4653-spec-intrinsics/plan.md`
- one append-only entry in `plan/log.md`

## Read-only files and directories

- `ESP32/`, `Camera/`, `Robot Arm_Claws/`
- device files and all deployment targets
- AprilTag board coordinates and drawing geometry

## Shared Dependencies

- OpenCV pinhole camera matrix and Brown distortion-vector convention
- runtime 1280x720 stream and the existing aspect-preserving intrinsic scaling
- supplied GC4653 native 2560x1440 resolution and H81/V51 degree field of view

## Risk and safety door

- Risk: an estimated camera model can bias metric AprilTag pose. It must not be
  presented as calibrated or production-ready.
- Hardware: none.
- User operations: none.
- Backup and recovery: Git for tracked files; the ignored local file contains no
  credential and remains recoverable from the example.
- Motion gate: no hardware connection or motion is authorized.

## Expected work

1. Express the same FOV-derived model at native 2560x1440 resolution so runtime
   scaling yields the existing 1280x720 matrix.
2. Mark distortion as unknown in the calibration identity and document that 5%
   alone lacks sign/model/radius information for `k1,k2,p1,p2,k3`.
3. Update deterministic parsing/scaling tests and validate the vision suite.

## Validation

- camera JSON parsing and intrinsic scaling tests
- applicable console vision tests
- `git diff --check`
- `git status --short --branch`

## Actual results

- Rebased the provisional matrix on native 2560x1440: `fx=1498.687444`,
  `fy=1509.511392`, `cx=1280`, `cy=720`. Existing aspect-preserving scaling
  produces the same runtime 1280x720 matrix (`749.343722`, `754.755696`,
  `640`, `360`), so recognition behavior is intentionally unchanged.
- Updated the safe example and ignored local calibration identity to state that
  distortion is unknown. Retained zero solver placeholders and
  `production_ready=false`; the supplied 5% scalar was not fabricated into a
  Brown distortion vector.
- Documented the independent 1525 px focal/pixel-pitch estimate and why rounded
  hardware specifications do not constitute image calibration.
- Both JSON files parsed. The 10 focused AprilTag tests and all 160 discovered
  app/console tests passed; `git diff --check` passed.
- No device connection, upload, process change, configuration deployment or
  motion occurred.

## Outstanding matters

- Checkerboard/ChArUco image calibration is still required before setting
  `production_ready=true` or trusting metric AprilTag pose.

## Experience signal (for manual review)


## Intent to submit

```text
docs(vision): define provisional GC4653 intrinsics
```
