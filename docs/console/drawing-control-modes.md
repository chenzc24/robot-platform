# Drawing relocation control modes

The unified PC runner exposes explicit `baseline`, `localized_baseline`, and
`advanced` selections. `localized_baseline` remains the only production
candidate; `baseline` is open-loop and `advanced` remains physically
unvalidated. They share the same device deployment and planner, and there is no
runtime fallback between them.

The drawing system uses one planner and one explicit PC-selected relocation
strategy. Copy `config/drawing-control.example.json` to the ignored
`config/drawing-control.local.json`; keep `production_ready` false until the
selected strategy has completed its own L3/L4 validation.

The full JSON canvas is immutable. `drawing.geometry.canvas_width_mm` and
`canvas_height_mm` define the physical drawing region. With the confirmed axis
formula, `user_y_offset_mm` is the JSON top-left origin's User-Y coordinate and
the corresponding User-Z coordinate is `user_z_offset_mm + canvas_height_mm`.
The unified runner requires JSON and board millimetres to match; legacy data may
use the explicit `--allow-uniform-canvas-rescale` option only when both axes
have the same scale. It never allows silent non-uniform stretching.

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

`baseline.initial_json_axis_offset_mm` defines the initial placement of the
immutable full-board JSON in the arm's current reach window. Its safe default is
zero. This is not measured by the Baseline runner: the operator must establish
the configured physical board/User0 relationship and starting chassis position.

## Localized Baseline

`selected_mode: localized_baseline` is the intermediate mode. It uses the same
bounded, refreshed direct `VELOCITY` movement as Baseline and never starts line
following. Once `STOP` returns, it also requires an exact `STATUS` report of
`enabled_stopped`, invalidates the old localization on motion intent, waits the
localization settling interval, and accepts only a newer stable AprilTag lock.

The planner's requested delta chooses the coarse direct distance. When its
centering suggestion exceeds `max_distance_mm`, the coordinator limits that
single direct hop to `max_distance_mm`, stops, obtains the mode-required fresh
localization, and replans from the same checkpoint. The relocator's direct-call
distance guard remains active. The measured result, rather than the unexecuted
remainder of the centering suggestion, determines whether another hop is
needed. In Localized Baseline, the corresponding open-loop estimate is never
used as the resumed drawing offset. The replacement
offset, rail position, generation and confidence all come from the new AprilTag
context. `baseline.settle_ms` belongs only to Baseline; Localized Baseline uses
the localization state's configured settling and sample windows.

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

All three strategies require explicit structured admission stating that an
operator is present, the physical emergency stop is ready, the arm is safe and
the chassis is `enabled_stopped`. The local control configuration must also be
`production_ready: true`. These software checks supplement rather than replace
the physical L3/L4 gate.

Mode selection occurs before movement. Localized Baseline or Advanced sensor /
AprilTag failure stops and returns an error; neither silently falls back to
another mode. A new operator/task decision may explicitly start a different
mode afterward. State-changing requests are not retried after an unknown
outcome.

The relocation strategies are implemented in
`src/console/drawing/control_modes.py` with injected chassis and localization
interfaces. Schema 2 adds the `localized_baseline` selection and its bounded
polling and lock timeout. Schema 1 remains accepted for existing Baseline and
Advanced configuration, but cannot select the new mode.

`relocate_reposition_plan` accepts only an incomplete plan whose final step is
`reposition.required` and returns the same checkpoint plus the new offset and
structured relocation evidence.

`app/run_drawing.py` is the common guarded PC entry point for image or JSON
input and all three explicit strategies. `app/localized_baseline_run.py` remains
a compatibility entry point. Dry-run is the default and opens no runtime
configuration or device connection. Real execution
requires the selected mode, production-ready drawing/control/vision/localization
configuration, exact job hash, a new durable log, arm and chassis profile
confirmations, current attended safety gates, and an initial AprilTag lock. It
then repeats:

```text
lock generation N → reserve localized task → execute one arm window
→ return pen and arm-safe pose → finish window → direct chassis move
→ STOP + enabled_stopped → lock generation N+1 → resume exact checkpoint
```

The runner owns the one ESP32 and one arm session; do not connect the UI's
manual device sessions at the same time. The UI may remain open for video and
its independently configured overlay, but the script's localization samples
and execution log are authoritative for the run. Any failure stops later
commands without automatic retry or checkpoint recovery. The shutdown path
attempts chassis `STOP` and `DISABLE`; these software actions do not replace the
physical emergency stop.

For `baseline`, the same loop starts at the configured initial offset and uses
the relocator's commanded open-loop offset after each barrier. For `advanced`,
it requires an initial lock, delegates station-seeking line following to ESP32,
and requires a newer lock before resuming. The drawing JSON is never rewritten.
