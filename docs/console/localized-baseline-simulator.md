# Localized Baseline coordinate rehearsal simulator

The simulator exercises the only recommended production chain without loading
runtime configuration or importing a real device client:

```text
normalized JSON -> fixed User0 Y/Z mapping -> one-axis AprilTag offset
-> reachable window -> exact checkpoint -> commanded open-loop rail move
-> independent true rail position -> logical STOP/enabled_stopped
-> new AprilTag measurement -> measured offset -> resumed window
```

It calls the production `execute_drawing` coordinator, which in turn calls the
production planner, drawing-window executor and `LocalizedBaselineRelocator`.
Only the arm, ESP32, AprilTag state and clock interfaces are deterministic fake
adapters. The simulator therefore executes the real timed `VELOCITY` refresh,
`STOP`, parsed `enabled_stopped`, fresh-generation wait and exact checkpoint
resume code without opening ESP32, MaixCam, robot-arm, RTSP or serial
connections.

## Run the full drawing rehearsal

The checked-in User-Y `-200..180` mm drawing window is inherited from the
colleague-tested first-generation arm program. The selected 700 x 200 mm
canvas uses `User-Y = 700u - 350 + offset` and therefore exceeds that 380 mm
window. The default rehearsal is consequently a configuration-faithful test of
checkpointing, chassis relocation, fresh AprilTag localization and resume. Run
it without a simulated reach override:

```powershell
python app/localized_baseline_sim.py dataset/dobot-generation-1.json `
  --site-config config/drawing.example.json `
  --motion-gain 0.96 `
  --stop-overshoot-mm 1.5 `
  --localization-errors-mm 0.4 `
  --rail-min-mm -500 `
  --rail-max-mm 500 `
  --force --open
```

The deterministic gain, overshoot and localization errors are simulator inputs,
not production calibration. A single localization-error value repeats at every
fresh AprilTag generation; a sequence instead supplies one value per generation
and deliberately fails if it is exhausted. Omit them for the simulator's
ideal-motion defaults.

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
- counts proving that production-path `VELOCITY`, `STOP`, `STATUS`, fresh-lock
  and arm commands were exercised.

Use `--rail-reference-mm`, `--initial-rail-position-mm`, and
`--json-mm-per-rail-mm` to rehearse a candidate calibration. The equation is:

```text
measured_json_axis_offset_mm = json_mm_per_rail_mm
                               * (measured_rail_position_mm
                                  - measured_reference_position_mm)
```

The production relocator first caps the planner's requested center shift to its
normal window target (160 mm in the template), then withholds the configured
approach reserve (20 mm) from its coarse move. The fake chassis integrates that
actual production `VELOCITY` call, then applies the fixed motion gain and signed
stop overshoot:

```text
commanded_rail_move_mm = requested_json_delta_mm / json_mm_per_rail_mm
actual_rail_move_mm = commanded_rail_move_mm * motion_gain
                      + sign(commanded_rail_move_mm) * stop_overshoot_mm
```

Only after the production relocator calls logical `STOP`, parses the returned
status and requests a new generation does the fake localization adapter add the
next declared error. It then performs bounded micro-moves toward the same target
until its new measured offset is within tolerance. The coordinator receives only
that final measured offset and calls the production planner again from the exact
checkpoint. Rail bounds, failed residual progress, exhausted adjustment attempts,
exhausted error samples and the production window limit fail the run instead of
being corrected for presentation.

The report also totals absolute rail travel and flags direction reversals. The
planner now exhausts all reachable color groups in a physical window and then
sweeps toward the lowest remaining drawing coordinate, rather than allowing
group/pen order to cause window ping-pong. A reported reversal remains an
operational review signal because it adds settling, backlash and localization
opportunities. The fixed gain/overshoot model exposes first-order errors but is
not a chassis dynamics model.

## Interpretation limits

This is an L1 User-Y drawing-window and chassis-relocation rehearsal. It does
not model:

- camera intrinsics, distortion, reprojection geometry or tag dropout; the
  declared localization errors are deterministic scalar samples only;
- acceleration, network delay, time-varying slip, chassis yaw or closed-loop
  motor dynamics; motion gain and stop overshoot are fixed scalars;
- physical standstill; `enabled_stopped` remains a logical ESP32 state.

Do not copy simulated error parameters into production configuration. Hardware
execution still needs the real common-board tag
coordinates, reference rail position `r0`, verified rail scale/sign and local
production-ready drawing/control configuration. Any L3/L4 run also needs the
fresh attended physical safety gate in `AGENTS.md`.
