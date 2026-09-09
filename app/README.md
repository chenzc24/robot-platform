# PC drawing tools

The standalone four-stroke `demo.py` has been removed. Baseline, Localized
Baseline and Advanced now share the grouped drawing loader, planner, pen
workflow and coworker motion profile. They differ only in the chassis
relocation strategy.

## Unified image or JSON entry point

`run_drawing.py` is the common PC entry point. It accepts an exported stroke
JSON directly, or sends PNG/JPEG/WebP/SVG input to the loopback StrokeReview
API. Image input always uses the physical canvas dimensions and contain-fit
margin from the unified `drawing.local.json`; generated `strokes.json`, `audit.json`, the full response
and an input manifest are retained under ignored `dataset/generated/` by
default and are never silently overwritten.

Start StrokeReview before using an image:

```powershell
.\stroke-review.cmd -SkipModels
python app/run_drawing.py .\picture.png
```

The default is a no-device dry run. Existing reviewed JSON uses the same entry:

```powershell
python app/run_drawing.py dataset/dobot-generation-1.json `
  --allow-uniform-canvas-rescale
```

The runner rejects a JSON whose `target_width_mm` or `target_height_mm` differs
from the configured physical canvas, preventing silent scale or aspect-ratio
changes. A legacy JSON with the same aspect ratio may be deliberately mapped to
the configured board with `--allow-uniform-canvas-rescale`; non-uniform stretch
is always rejected. The produced or loaded JSON hash is recorded automatically.

All modes use the same device deployment. `baseline` begins with
`baseline.initial_json_axis_offset_mm` and subsequently trusts commanded direct
travel. `localized_baseline` uses direct travel plus a fresh AprilTag lock.
`advanced` uses ESP32 line following plus a fresh lock. There is no automatic
fallback between modes. Localized Baseline remains the only production
candidate until the other strategies receive their own physical validation.
The single `relocation.selected_mode` value in `drawing.local.json` selects the
strategy for both dry-run and execution.

## Grouped drawing preview

Import the delivered Dobot project data as documented in
[PC grouped drawing planning](../docs/robot-arm/pc-drawing-task.md), then preview
the ignored dataset with the ignored local configuration:

```powershell
python app/drawing_task.py dataset/dobot-generation-1.json `
  --config config/drawing.local.json --show-steps
```

`drawing_task.py` remains preview-only: it opens no device connection and
sends no motion. The formal configuration uses the selected 700 x 200 mm
canvas while preserving the coworker project's parameterized User-Y/Z mapping,
51 mm pen travel, home joints, P1-P4 rack poses, 60/30 mm rack depths, 60/1 mm
gripper widths, drawing speed 35%, and `cp=100`. Its 700 mm width exceeds the
retained `-200..180` mm User-Y window, so normal Localized Baseline execution
must divide the job into reachable windows and relocate the chassis. Motions
without a source-explicit speed use the project owner's clarified 50% default,
and every arm motion uses 20% acceleration.

`baseline_run.py` remains an internal arm-only diagnostic. Its default is
dry-run. Real execution accepts only a complete plan with no reposition barrier,
requires the site's single `production_ready=true` plus `--attended`, then
requires ready YOLO status and valid feedback before the first motion. It
opens no chassis session. Every command must return `DONE`; fault, rejection,
unknown outcome or disconnect stops all later commands without retry or
automatic resume.

`localized_baseline_run.py` remains a compatibility production-candidate entry point:
direct chassis motion without line following, followed by a mandatory fresh
AprilTag lock. It returns the pen and reaches the configured safe home at every
planner barrier, replaces the open-loop travel estimate with the measured
one-axis offset, and resumes the exact checkpoint. It uses the same deployed
ESP32, MaixCam and arm services as the other modes; only PC orchestration differs.

`baseline_run.py` remains the older arm-only diagnostic path. Advanced
line-following remains physically unvalidated; neither is an automatic fallback.

## Localized Baseline coordinate rehearsal

Before using hardware, generate a self-contained simulated canvas and step
through the exact window/checkpoint sequence:

```powershell
python app/localized_baseline_sim.py dataset/dobot-generation-1.json `
  --site-config config/drawing.example.json `
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

After a reviewed local config has `production_ready=true`, the normal real-run
command is `python app/run_drawing.py <input> --execute --attended`. The runner
generates a unique JSONL log path automatically. It never resumes automatically
after an unknown outcome.

Localized Baseline dry-run reads the same unified site file, but does not load
endpoint configuration or connect to a device:

```powershell
python app/localized_baseline_run.py dataset/dobot-generation-1.json `
  --site-config config/drawing.local.json
```

Localized execution additionally needs the endpoint-only console configuration,
enabled inline AprilTag data, and `selected_mode: localized_baseline`.
Do not connect the UI manual chassis/arm sessions concurrently with the script.

## AprilTag localization

`apriltag_calibration.py` is an observation-only PC entry point. It reads an
image or RTSP stream, reuses `src/console/vision`, and emits board pose matrices,
confidence and reprojection diagnostics as JSON. It never opens arm or chassis
command routes. See
[PC AprilTag board localization](../docs/console/apriltag-localization.md).

`apriltag_board_calibration.py` is the separate one-time layout builder. Its
`capture` command records decoded pixel corners at manually selected stopped
positions; its `solve` command holds measured anchor corners fixed and expands
them into one connected planar board. See
[AprilTag planar board calibration](../docs/console/apriltag-board-calibration.md).

## Local validation

```powershell
python -m unittest tests.app.test_drawing_task `
  tests.console.test_drawing_job tests.console.test_drawing_control_modes
```
