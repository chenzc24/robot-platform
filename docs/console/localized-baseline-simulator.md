# Localized Baseline coordinate rehearsal simulator

The simulator exercises the only recommended production chain without loading
runtime configuration or importing a device client:

```text
normalized JSON -> fixed User0 Y/Z mapping -> one-axis AprilTag offset
-> reachable window -> exact checkpoint -> ideal direct rail move
-> logical STOP/enabled_stopped -> new generation -> resumed window
```

It calls the production drawing loader and `build_drawing_plan`. The simulator
does not copy the planner's reach/barrier logic, and it never opens ESP32,
MaixCam, robot-arm, RTSP or serial connections.

## Run the full drawing rehearsal

The checked-in example drawing geometry spans User-Y `-200..180` mm, so the
150 mm sample drawing normally fits one window. To force a meaningful
multi-window exercise, use an explicitly simulated narrower interval:

```powershell
python app/localized_baseline_sim.py dataset/dobot-generation-1.json `
  --drawing-config config/drawing.example.json `
  --simulated-reachable-min-mm -60 `
  --simulated-reachable-max-mm 60 `
  --force --open
```

The default report is written to ignored temporary output:

```text
tmp/localized-baseline-rehearsal.html
```

The report contains no network dependencies. It provides:

- a User0 Y/Z view of completed, current, pending and unreachable segments;
- a window selector and exact checkpoint trace;
- rail reference/current positions and localization generations;
- a normalized `(u,v)` coordinate probe showing relative Y/Z and absolute
  User-Y for the selected window;
- the complete safe-barrier sequence before every simulated rail movement.

Use `--rail-reference-mm`, `--initial-rail-position-mm`, and
`--json-mm-per-rail-mm` to rehearse a candidate calibration. The equation is:

```text
json_axis_offset_mm = json_mm_per_rail_mm
                    * (rail_position_mm - rail_reference_mm)
```

The simulator satisfies each planner barrier at the exact suggested offset and
assumes the next localization result is perfect. A positive simulated rail move
with scale `-1` therefore produces an equal negative JSON-axis offset.

The report also totals absolute rail travel and flags direction reversals. A
reversal is not automatically a planner defect: group/pen order and a narrow
reachable interval can legitimately require it. It is an operational review
signal because extra direction changes add settling, backlash and localization
opportunities that this ideal simulator does not model.

## Interpretation limits

This is an L1 coordinate and state-sequence rehearsal. It does not model:

- camera intrinsics, distortion, reprojection error or tag dropout;
- wheel slip, acceleration, network delay, stop distance or chassis yaw;
- robot kinematics, singularity, collision clearance or pen contact;
- physical standstill; `enabled_stopped` remains a logical ESP32 state.

Do not copy simulated reach overrides into production configuration. Tomorrow's
hardware session still needs the measured camera calibration, common-board tag
corners, reference rail position `r0`, verified rail scale/sign, safe Home, User0
axis direction, real Y/Z offsets and pen travel. Any L3/L4 run also needs the
fresh attended physical safety gate in `AGENTS.md`.
