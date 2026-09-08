# PC drawing tools

The standalone four-stroke `demo.py` has been removed. Baseline and Advanced
now share the grouped drawing loader, planner, pen workflow and coworker motion
profile. They differ only in the chassis relocation strategy.

## Grouped drawing preview

Import the delivered Dobot project data as documented in
[PC grouped drawing planning](../docs/robot-arm/pc-drawing-task.md), then preview
the ignored dataset with the ignored local configuration:

```powershell
python app/drawing_task.py dataset/dobot-generation-1.json `
  --config config/drawing.local.json --show-steps
```

`drawing_task.py` remains preview-only: it opens no device connection and
sends no motion. The formal configuration preserves the coworker project's
150 mm canvas, User-Y/Z mapping, 51 mm pen travel, home joints, P1-P4 rack
poses, 60/30 mm rack depths, 60/1 mm gripper widths, drawing `v=12`, and
`cp=100`. Motions without a source-explicit speed use the project owner's
clarified 50% default, and every arm motion uses 20% acceleration.

`baseline_run.py` adds a separate guarded arm-only execution entry point. Its
default is still dry-run. Real execution accepts only a complete plan with no
reposition barrier, requires `production_ready=true`, an exact job-hash
confirmation, four explicit attended-safety flags and a new durable log path,
then requires ready YOLO status and valid feedback before the first motion. It
opens no chassis session. Every command must return `DONE`; fault, rejection,
unknown outcome or disconnect stops all later commands without retry or
automatic resume.

The upgraded MaixCam/RPA2 route carries drawing `blend_pct=100` to the
controller's `RelMovLUser` `cp` option. Deploy the compatible controller project
before MaixCam. Do not use the real execution entry point with an older endpoint.

Dry-run remains the default:

```powershell
python app/baseline_run.py dataset/dobot-generation-1.json `
  --config config/drawing.local.json
```

After a reviewed local config has `production_ready=true`, a real run additionally
requires `--execute`, the exact dry-run `job_sha256`, a new `--log` path, and all
four `--confirm-*` safety flags shown by `--help`. Never reuse an existing log or
resume automatically after an unknown outcome.

## AprilTag localization

`apriltag_calibration.py` is an observation-only PC entry point. It reads an
image or RTSP stream, reuses `src/console/vision`, and emits board pose matrices,
confidence and reprojection diagnostics as JSON. It never opens arm or chassis
command routes. See
[PC AprilTag board localization](../docs/console/apriltag-localization.md).

## Local validation

```powershell
python -m unittest tests.app.test_drawing_task `
  tests.console.test_drawing_job tests.console.test_drawing_control_modes
```
