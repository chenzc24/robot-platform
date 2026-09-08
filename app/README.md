# PC drawing tools

The standalone four-stroke `demo.py` has been removed. Baseline, Localized
Baseline and Advanced now share the grouped drawing loader, planner, pen
workflow and coworker motion profile. They differ only in the chassis
relocation strategy.

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

`localized_baseline_run.py` is the only normal production-candidate entry point:
direct chassis motion without line following, followed by a mandatory fresh
AprilTag lock. It returns the pen and reaches the configured safe home at every
planner barrier, replaces the open-loop travel estimate with the measured
one-axis offset, and resumes the exact checkpoint. It uses the same deployed
ESP32, MaixCam and arm services as the other modes; only PC orchestration differs.

`baseline_run.py` remains an internal arm/chassis diagnostic path. Advanced
line-following remains a future strategy; neither is an automatic fallback.

## Localized Baseline coordinate rehearsal

Before using hardware, generate a self-contained simulated canvas and step
through the exact window/checkpoint sequence:

```powershell
python app/localized_baseline_sim.py dataset/dobot-generation-1.json `
  --drawing-config config/drawing.example.json `
  --simulated-reachable-min-mm -60 `
  --simulated-reachable-max-mm 60 `
  --force --open
```

This command imports no device client and opens no connection. The reach
override exists only to force a multi-window exercise; it does not update local
or production configuration. See
[the simulator guide](../docs/console/localized-baseline-simulator.md).

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

Localized Baseline dry-run also requires the schema-2 drawing-control file, but
does not load runtime configuration or connect to a device:

```powershell
python app/localized_baseline_run.py dataset/dobot-generation-1.json `
  --drawing-config config/drawing.local.json `
  --control-config config/drawing-control.local.json
```

For real execution, review `--help`. In addition to the Baseline gates it needs
the ignored schema-5 console configuration with production-ready AprilTag files,
`selected_mode: localized_baseline`, and explicit chassis-profile confirmation.
Do not connect the UI manual chassis/arm sessions concurrently with the script.

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
