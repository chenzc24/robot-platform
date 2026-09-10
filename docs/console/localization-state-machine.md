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
eight, or more uniquely identified tags distributed along the rail. The current
production solver compares decoded tag centers with the saved JSON-zero center
reference and publishes one scalar directly:

```text
rail_position_mm = center_delta_mm
```

All tags need not be visible together. Adjacent regions should overlap so two
or more tags are normally visible during handoff. Changing visible IDs does not
reset a sample window; changing the layout ID, center-reference ID or board
frame does. Two or more tags are required in the current field profile so their
independent displacement and cross-axis residuals can be compared.

Camera intrinsics, tag size and fitted corner orientation are not used by the
center-delta solver. They remain inputs only to the optional full-pose PnP
diagnostic. No depth camera or full camera-to-arm extrinsic is required.

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
the configured visible-tag count, a ready center reference, and scalar position
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

## Center-delta production model

For the current rail-only installation, `localization.method: center_delta`
is the production model. It deliberately does not solve a three-dimensional
camera pose. At the JSON-zero chassis position, four or more decoded tag
centers define one reference homography from pixels to measured board-center
coordinates. Later frames map each visible tag center through that same
reference:

```text
q_i = H_zero(pixel_center_i)
rail_delta_i = tag_world_axis_i - q_i.axis
rail_position_mm = median(rail_delta_i)
```

The fixed camera-to-base displacement cancels. At runtime two visible tags are
enough because the homography is not re-solved; each tag independently measures
the one remaining translation degree of freedom. Tag disagreement and the
mapped cross-axis residual reject camera yaw, lateral movement, a loose mount,
or a bad landmark. The camera height and attitude must remain the same as the
zero reference. A mounting change requires a new center reference.

`center_delta` uses measured tag centers only. Camera intrinsics, distortion,
the printed square size, and fitted tag-corner orientations are not part of the
rail estimate. The former four-corner PnP path remains available as
`localization.method: pose_pnp` for diagnostics and future full-pose work.

Example additional localization fields:

```json
{
  "method": "center_delta",
  "center_reference": {
    "production_ready": true,
    "reference_id": "site-zero-v1",
    "image_width": 1280,
    "image_height": 720,
    "tag_centers_px": {
      "0": [793.091, 191.620],
      "1": [779.624, 587.707],
      "4": [390.070, 604.638],
      "5": [410.524, 210.003]
    },
    "max_tag_disagreement_mm": 15.0,
    "max_cross_axis_error_mm": 15.0
  }
}
```

Localization also requires enabled AprilTag detection. PnP requires
production-ready camera and board-corner calibration; center-delta instead
requires a production-ready zero reference. `GET
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
