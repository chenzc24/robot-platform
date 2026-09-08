# Drawing relocation control modes

The drawing system uses one planner and one explicit PC-selected relocation
strategy. Copy `config/drawing-control.example.json` to the ignored
`config/drawing-control.local.json`; keep `production_ready` false until the
selected strategy has completed its own L3/L4 validation.

## Baseline

`selected_mode: baseline` does not read line sensors or AprilTag results. Given
a planner-requested JSON-axis delta, it converts back to rail distance using
`json_mm_per_rail_mm`, sends the existing direct `VELOCITY` command at the
configured speed, refreshes before the ESP32 hold expires, and always attempts
`STOP`. It then waits the configured settling interval and adds the requested
delta to the previous JSON offset.

This value is explicitly reported as `commanded_open_loop`, with no measured
rail position, localization generation, or confidence. Speed multiplied by PC
elapsed time ignores wheel slip, acceleration, network delay and stop distance.
It is a temporary baseline, not absolute positioning.

## Advanced

`selected_mode: advanced` sends `LINE_FOLLOW_START` with direction only. ESP32
owns GPIO sampling, steering correction, station debounce, scheduler timing and
local stop. The PC polls `LINE_FOLLOW_STATUS`; station, fault and timeout remain
observable. Direct `VELOCITY` is rejected while the follower is active.

After station confirmation the PC sends `LINE_FOLLOW_STOP`, asks the existing
localization state machine to relocalize, keeps the ESP32 session healthy with
PING, and accepts only a newer locked AprilTag generation. The result reports
`apriltag_locked`, measured rail position, generation and minimum confidence.
The requested reposition magnitude currently selects direction to the next
station; station placement determines the coarse distance.

## Admission and failure

Both strategies require explicit structured admission stating that an operator
is present, the physical emergency stop is ready, the arm is safe and the
chassis is `enabled_stopped`. The local control configuration must also be
`production_ready: true`. These software checks supplement rather than replace
the physical L3/L4 gate.

Mode selection occurs before movement. Advanced sensor or AprilTag failure
stops and returns an error; it never silently falls back to baseline. A new
operator/task decision may explicitly start a baseline relocation afterward.
State-changing requests are not retried after an unknown outcome.

The relocation strategies are implemented in
`src/console/drawing/control_modes.py` with injected chassis and localization
interfaces. The coordinated drawing executor should consume a
`reposition.required` checkpoint, invoke the selected relocator, pass the
resulting `json_axis_offset_mm` into the existing planner, and resume. No UI or
automatic full drawing execution route is enabled by this change.

`relocate_reposition_plan` provides that exact boundary: it accepts only an
incomplete plan whose final step is `reposition.required` and returns the same
checkpoint plus the new offset and structured relocation evidence.
