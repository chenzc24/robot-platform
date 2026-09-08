# Localized Baseline coordinate rehearsal simulator

The simulator exercises the only recommended production chain without loading
runtime configuration or importing a device client:

```text
normalized JSON -> fixed User0 Y/Z mapping -> one-axis AprilTag offset
-> reachable window -> exact checkpoint -> commanded open-loop rail move
-> independent true rail position -> logical STOP/enabled_stopped
-> new AprilTag measurement -> measured offset -> resumed window
```

It calls the production drawing loader and `build_drawing_plan`. The simulator
does not copy the planner's reach/barrier logic, and it never opens ESP32,
MaixCam, robot-arm, RTSP or serial connections.

## Run the full drawing rehearsal

The checked-in example drawing geometry spans User-Y `-200..180` mm, so the
150 mm sample drawing normally fits one window. That is the configuration-faithful
result and must not be reported as a relocation test. To run a separate physical
stress scenario, declare a narrower hypothetical reach and fixed error parameters
that are independent of planner output:

```powershell
python app/localized_baseline_sim.py dataset/dobot-generation-1.json `
  --drawing-config config/drawing.example.json `
  --simulated-reachable-min-mm -60 `
  --simulated-reachable-max-mm 60 `
  --motion-gain 0.96 `
  --stop-overshoot-mm 1.5 `
  --localization-errors-mm 0.4,-0.3,0.8,-0.6,0.2,-0.1,0.5,-0.2,0.3,-0.4,0.1,0.0 `
  --rail-min-mm -150 `
  --rail-max-mm 150 `
  --force --open
```

The default report is written to ignored temporary output:

```text
tmp/localized-baseline-rehearsal.html
```

The report contains no network dependencies. It provides:

- a User0 Y/Z view of completed, current, pending and unreachable segments;
- a window selector and exact checkpoint trace;
- true and measured rail reference/current positions and localization generations;
- a normalized `(u,v)` coordinate probe showing relative Y/Z and absolute
  User-Y for the selected window;
- the complete safe-barrier sequence before every simulated rail movement.

Use `--rail-reference-mm`, `--initial-rail-position-mm`, and
`--json-mm-per-rail-mm` to rehearse a candidate calibration. The equation is:

```text
measured_json_axis_offset_mm = json_mm_per_rail_mm
                               * (measured_rail_position_mm
                                  - measured_reference_position_mm)
```

The planner's requested JSON-axis delta is converted to an open-loop chassis
command using the configured scale. The independently simulated chassis then
applies the fixed motion gain and signed stop overshoot:

```text
commanded_rail_move_mm = requested_json_delta_mm / json_mm_per_rail_mm
actual_rail_move_mm = commanded_rail_move_mm * motion_gain
                      + sign(commanded_rail_move_mm) * stop_overshoot_mm
```

Only after logical STOP does the simulator add the next declared localization
error, calculate a fresh measured offset, and call the production planner again
from the exact checkpoint. It does not replace the measured result with the
planner target. Rail bounds, zero progress, exhausted error samples and the
window limit fail the run instead of being corrected for presentation.

The report also totals absolute rail travel and flags direction reversals. A
reversal is not automatically a planner defect: group/pen order and a narrow
reachable interval can legitimately require it. It is an operational review
signal because extra direction changes add settling, backlash and localization
opportunities. The fixed gain/overshoot model exposes first-order errors but is
not a chassis dynamics model.

## Interpretation limits

This is an L1 coordinate and state-sequence rehearsal. It does not model:

- camera intrinsics, distortion, reprojection geometry or tag dropout; the
  declared localization errors are deterministic scalar samples only;
- acceleration, network delay, time-varying slip, chassis yaw or closed-loop
  motor dynamics; motion gain and stop overshoot are fixed scalars;
- robot kinematics, singularity, collision clearance or pen contact;
- physical standstill; `enabled_stopped` remains a logical ESP32 state.

Do not copy simulated reach overrides into production configuration. Tomorrow's
hardware session still needs the measured camera calibration, common-board tag
corners, reference rail position `r0`, verified rail scale/sign, safe Home, User0
axis direction, real Y/Z offsets and pen travel. Any L3/L4 run also needs the
fresh attended physical safety gate in `AGENTS.md`.
