# GC4653 and rectangular-board precalibration defaults

- Status: completed
- Responsible: agent implementation from user-supplied camera specifications
- Highest validation level: L1

## Objective

Populate the AprilTag v1 examples with a GC4653 1280 x 720 field-of-view-based
intrinsic estimate and an explicit four-tag rectangular default layout. Allow
these unmeasured values to drive detection overlays and tentative transforms,
but ensure they can never produce `accepted=true` until both camera and board
files are marked as measured/production-ready.

## Initial state of the workspace

```text
## target/apriltag-pc-calibration-v1...origin/target/apriltag-pc-calibration-v1
 M .vscode/settings.json
 M app/demo.py
 M plan/log.md
?? plan/2026-09-03-arm-xyz-singularity-diagnosis/
?? plan/2026-09-03-arm-yz-drawing-review/
?? plan/2026-09-03-video-stream-diagnosis/
```

All listed dirty paths predate this follow-up and remain outside scope. The
existing unstaged XYZ log hunk must not enter the follow-up commit.

## Modifiable files

- `config/camera-calibration.example.json`
- `config/apriltag-board.example.json`
- `src/console/vision/`
- `src/console/web_console/static/app.js`
- `tests/console/test_apriltag_vision.py`
- `docs/console/apriltag-localization.md`
- ignored `config/camera-calibration.local.json`,
  `config/apriltag-board.local.json`, and the vision-only/schema fields in
  `config/console.local.json`
- this plan and an appended `plan/log.md` section

## Read-only files and directories

- `.vscode/settings.json`, `app/demo.py`, existing diagnostic plans/log hunk
- `ESP32/`, `Camera/`, `Robot Arm_Claws/`, `tmp/`
- existing endpoint/credential/device fields in local configuration and all
  device files/processes
- motion routes, protocols, limits and deployed services

## Shared dependencies

- Current source stream is 1280 x 720, while the supplied GC4653 native mode is
  2560 x 1440; both are 16:9 so the inferred focal lengths scale by one half.
- Supplied field of view: H81 degrees and V51 degrees. Pinhole estimate uses
  `fx=(width/2)/tan(HFOV/2)` and `fy=(height/2)/tan(VFOV/2)`.
- Supplied 5% lens-distortion summary is not an OpenCV coefficient vector;
  distortion remains a zero placeholder and must be measured.
- Existing default board uses four 40 mm tags at the corners of a 300 x 200 mm
  rectangle; these dimensions remain explicitly unmeasured.

## Risk and safety gate

- Risk: an inferred pinhole model or default board can yield plausible but
  metrically incorrect transforms. Both examples remain `production_ready:
  false`; runtime must solve only a tentative pose and force `accepted=false`.
- Hardware: none. No RTSP/device connection or motion.
- User operations: later measure the printed tag corners and calibrate the
  actual lens/focus/resolution before setting either readiness flag to true.
- Backup and recovery: Git rollback only.
- Motion gate: not applicable; observation-only pipeline remains unchanged.

## Expected work

1. Fill the camera example with the documented GC4653/FOV estimate and identify
   the board example as an unmeasured rectangular default.
2. Preserve readiness flags in loaded models and publish them in results.
3. Solve tentative transforms with unready data but force a distinct
   `precalibration` state and prevent acceptance.
4. Add regressions and document exact assumptions and upgrade path.
5. Create ignored local precalibration copies and upgrade only the local schema
   and disabled vision section, preserving all existing device settings.

## Validation

- focused calibration/localizer tests
- complete Python and JavaScript regression suites
- Python compile, `git diff --check`, scoped staged-diff review and branch sync

## Actual results

- Filled the tracked and ignored local camera files with the 1280 x 720
  GC4653 pinhole estimate: fx 749.343722 px, fy 754.755696 px, principal point
  (640, 360), and zero placeholder distortion. Both remain unready.
- Identified the existing four-tag default as an unmeasured 300 x 200 mm outer
  rectangle with 40 mm tags and created the ignored local copy.
- Calibration loaders now preserve the readiness flags. Unready inputs can
  produce boxes and a tentative transform but always return `precalibration`,
  `calibration_inputs_unverified`, and `accepted=false`; the UI and JSONL logs
  expose both readiness flags and the UI labels `UNVERIFIED DEFAULTS`.
- Upgraded ignored `config/console.local.json` from schema 3 to 4 by adding only
  the vision section and preserving existing endpoint/device fields. Vision is
  left disabled, so no RTSP connection is started by this change.
- L1 passed: 309 Python tests across all suites, 14 JavaScript tests, Python
  compilation, JavaScript syntax and `git diff --check`. Focused coverage
  verifies the FOV numbers, measured-ready behavior and the forced-unaccepted
  tentative pose. No RTSP/device connection or motion occurred.

## Outstanding matters

- Physical camera and board calibration remain required.
- The 5% lens-distortion specification remains unusable as an OpenCV coefficient
  vector; actual distortion must be measured at the operating lens/focus/mode.

## Experience signal (for manual review)


## Intent to submit

```text
feat(vision): add safe GC4653 precalibration defaults
```
