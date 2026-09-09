# One-dimensional rail localization state machine

## Actual system model

The chassis and robot-arm base are treated as one rigid assembly that translates
only along one fixed rail axis. The drawing JSON is already correct at a known
rail origin. Relocalization therefore does not solve or consume a camera-to-base
or Tool0-to-pen transform. It computes one additive JSON-axis correction:

```text
rail_delta_mm = rail_position_mm - json_origin_rail_position_mm
json_axis_offset_mm = json_mm_per_rail_mm * rail_delta_mm
adjusted_axis_mm = original_axis_mm + json_axis_offset_mm
```

Normally `json_mm_per_rail_mm` is `-1`: moving the arm base +100 mm means the
same fixed drawing target is commanded 100 mm in the opposite local direction.
The sign and scale are explicit configuration because the drawing JSON axes and
the AprilTag board axes may use different conventions.

The unknown fixed camera-to-arm-base displacement cancels between the JSON-origin
observation and the current observation. The fixed pen/TCP offset also cancels
for relocation as long as the pen mounting, tool selection, drawing plane and
initial taught JSON-to-arm mapping remain unchanged. Those items still matter to
initial drawing accuracy, but they are not inputs to this state machine.

## AprilTag rail position

The AprilTag layout defines one metric `board_frame`. It may contain four,
eight, or more uniquely identified tags distributed along the rail. Every tag's
measured four corners belong to that same frame. The PC pose solver already
publishes `T_board_from_camera`; localization reads only one translation value:

```text
rail_position_mm = T_board_from_camera[rail_axis][3]
```

All tags need not be visible together. Adjacent regions should overlap so two
or more tags are normally visible during handoff. Changing visible IDs does not
reset a sample window; changing the layout ID, camera-calibration ID or board
frame does. A single tag can be allowed by setting `min_visible_tags` to 1, but
two or more provide stronger cross-checking.

Camera intrinsics, tag sizes and measured tag corners remain necessary for the
AprilTag solver to produce a metric camera position. No depth camera or full
camera-to-arm extrinsic is required for the one-dimensional relocation delta.

## States and command chain

```text
JSON referenced to known origin
        ↓
initial AprilTag rail lock
        ↓
execute reachable task section
        ↓
arm returns to a separately defined safe pose
        ↓
coarse chassis move ──→ old lock invalid immediately
        ↓
ESP32 reports enabled_stopped
        ↓
settling → collecting unique accepted frames → locked generation N+1
        ↓
apply json_axis_offset_mm to the remaining JSON points
```

Localization states are `disabled`, `blocked`, `invalid`, `moving`, `settling`,
`collecting`, and `locked`. A lock requires a bounded window of unique frames,
the configured visible-tag count, ready camera/layout data, and scalar position
spread within `max_position_spread_mm`.

Any possible chassis motion or lost chassis state invalidates the lock. Arm
motion does not, because it does not move the chassis-mounted camera or arm base.
The ESP32 `enabled_stopped` report is logical controller state, not measured
wheel or IMU velocity; the settling timer is not proof of physical standstill.

## Configuration

The unified drawing-site schema separates the rail datum/reference from the
localization sampling policy:

```json
{
  "rail": {
    "physical_start_mm": 0.0,
    "physical_travel_mm": null,
    "json_origin_rail_position_mm": 0.0,
    "json_mm_per_rail_mm": -1.0,
    "start_tolerance_mm": 3.0
  },
  "localization": {
    "enabled": false,
    "rail_axis": "x",
    "json_axis": "x",
    "settle_time_ms": 2000,
    "sample_window_ms": 3000,
    "min_valid_samples": 8,
    "min_visible_tags": 2,
    "max_position_spread_mm": 2.0
  }
}
```

`json_origin_rail_position_mm` is the camera's AprilTag-derived rail position
when the original JSON is known to draw correctly. It absorbs the unknown fixed
camera/base offset. It is not required to equal `physical_start_mm`, which is a
mechanical rail datum rather than an AprilTag observation. Apply
`json_axis_offset_mm` only after the selected JSON
coordinate has been converted to millimetres.

Localization also requires enabled, production-ready AprilTag vision. `GET
/api/state` publishes state, reason, generation, sample count and the locked
scalar context. `POST /api/localization/relocalize` restarts settling only when
the chassis is confirmed stopped and no localized task is active. Automatic
state changes write concise sanitized events without per-frame log noise.

## Future task interface

The transport-neutral runtime API remains:

```python
context = runtime.begin_localized_task("draw-42", expected_generation=7)
offset_mm = context["json_axis_offset_mm"]
runtime.finish_localized_task("draw-42", "DONE", "complete")

# Read without reserving the task slot:
context = runtime.localized_task_context(expected_generation=7)
```

The context is a deep copy containing the scalar position/offset, axes,
direction/scale, generation and source quality evidence. A generation check
prevents queued work from using a newer location silently. Only one localized
task may be active. Chassis motion marks it `UNKNOWN`; the executor must stop
sending later commands.

There is intentionally no generic HTTP task-execution route. The future drawing
executor must own stroke splitting, arm-safe-pose confirmation, coarse chassis
movement, fresh rail lock, offset application, workspace checks and terminal
arm-command handling.

## Validation boundary

L1 covers scalar projection, axis/sign configuration, unique-frame fusion,
changing visible tag sets, generation/task handling and motion invalidation. It
does not validate the real eight-tag layout, the JSON-origin scalar, rail
straightness, physical standstill, initial TCP/drawing calibration or L4 motion.
