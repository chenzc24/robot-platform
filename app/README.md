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

The current MaixCam/RPA2 primitive route still forces blending to zero.
Therefore the preview records the requested `cp=100`, but exact execution of
that blend remains a separately reviewed cross-device executor/protocol change.

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
