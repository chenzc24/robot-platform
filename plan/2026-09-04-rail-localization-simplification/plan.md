# Simplify localization to one-dimensional rail offsets

- Status: complete; submission pending
- Responsible: agent implementation and offline validation
- Highest validation level: L1

## Objective

Replace the general camera/base/tool SE(3) localization model in open PR #5
with the actual constrained system: the chassis and arm base translate only
along one fixed rail axis. After every logical stop, project the accepted
AprilTag board pose onto that configured axis, fuse a bounded window of unique
frames, lock one scalar rail position, and expose the additive JSON-axis offset
relative to the JSON's known rail origin. Preserve generation-checked task
lifecycle interfaces and issue no hardware command from localization itself.

## Workspace audit

```text
## target/localization-lock-state-machine...origin/target/localization-lock-state-machine
 M .vscode/settings.json
 M app/demo.py
 M plan/log.md
?? pelican-bicycle.svg
?? plan/2026-09-03-arm-xyz-singularity-diagnosis/
?? plan/2026-09-03-arm-yz-drawing-review/
?? plan/2026-09-03-video-stream-diagnosis/
```

All listed paths predate this goal or belong to other work. They remain
protected. Only a new appended `plan/log.md` hunk may be staged.

## Modifiable files

- `src/console/localization/`
- `src/console/runtime_config.py`
- `src/console/web_console/runtime.py` for scalar lock-event evidence
- `config/console.example.json`
- removal of the superseded robot-geometry example and ignore entry
- focused tests under `tests/console/`
- console/AprilTag documentation and README links
- this plan and a new appended `plan/log.md` section
- PR #5 title/body after the implementation is validated

## Read-only files and directories

- `.vscode/settings.json`, `app/demo.py`, the existing unstaged `plan/log.md`
  hunk, `pelican-bicycle.svg`, and the three diagnostic plan directories
- device source under `src/esp32/`, `src/maixcam/`, `src/robot_arm/`
- device files, ignored raw archives, and real local configuration
- chassis/arm protocols, manual arm behavior, and physical motion parameters

## Design contract

- The AprilTag layout defines one global board frame and may contain eight or
  more unique IDs distributed along the rail; not all tags need be visible.
- `T_board_from_camera[rail_axis][3]` is the observed camera position along the
  rail. The unknown fixed camera-to-arm-base displacement cancels when compared
  with the configured camera rail position at the JSON origin.
- The locked command adjustment is additive after JSON coordinates are in
  millimetres:

  ```text
  rail_delta_mm = rail_position_mm - json_origin_rail_position_mm
  json_axis_offset_mm = json_mm_per_rail_mm * rail_delta_mm
  adjusted_axis_mm = original_axis_mm + json_axis_offset_mm
  ```

- `json_mm_per_rail_mm` captures direction and scale; normally it is `-1`.
  This is the only required axis relationship, not a 6DoF camera/base extrinsic.
- Pen/TCP and initial JSON-to-arm alignment are outside relocalization. They are
  assumed unchanged from the taught working setup and therefore cancel for the
  relocation delta.
- Any possible chassis motion invalidates the scalar lock. Arm motion does not.
  Existing manual/Yolo arm commands remain independent.
- Logical `enabled_stopped` plus settling is not measured physical standstill.

## Expected work

1. Replace geometry/SE(3) configuration with rail axis, JSON axis, JSON-origin
   position, direction/scale, sample count/window and position-spread limits.
2. Fuse unique accepted AprilTag observations into a scalar mean rail position;
   allow changing visible tag subsets from one shared layout.
3. Lock and publish rail position, delta, additive JSON offset, generation and
   quality/source evidence; retain task context/begin/finish APIs.
4. Remove the now-unneeded camera/base and Tool0/pen geometry model and update
   documentation to explain exactly what cancels and which assumptions remain.
5. Add deterministic tests for sign/axis projection, large-layout tag handoff,
   frame uniqueness, stability, invalidation and runtime/API compatibility.

## Validation

- focused localization, vision and web-console tests
- complete console test suite
- all repository Python suites and browser JavaScript suite
- Python compilation, JavaScript syntax and JSON parsing
- `git diff --check`, staged diff review and final branch synchronization

L1 cannot verify rail straightness, AprilTag placement, physical stop, metric
camera calibration, sign convention, JSON alignment, pen setup or drawing error.

## Actual results

- Replaced the full camera/base/tool geometry loader and SE(3) fusion with a
  scalar `RailLocalizationStateMachine`. It projects
  `T_board_from_camera[rail_axis][3]`, averages unique accepted frames and
  locks `rail_position_mm`, rail delta and additive `json_axis_offset_mm`.
- Schema-5 localization now contains only rail axis, JSON axis, JSON-origin
  camera position, direction/scale and temporal/stability thresholds. The
  obsolete robot geometry file and ignore entry were removed.
- Preserved chassis invalidation, settling, generation-checked immutable task
  context, begin/finish lifecycle, relocalize HTTP route and independent manual
  arm behavior. Locked events now record scalar position, offset, sample count
  and minimum confidence without per-frame log noise.
- Confirmed the existing board schema accepts eight unique rail landmarks and
  that changing visible tag subsets does not reset a shared-layout sample
  window. A synthetic oblique AprilTag pose feeds the scalar lock directly.
- L1 passed 324 Python tests across all repository suites, including 122 console
  tests, plus 14 browser JavaScript tests. Python compilation, JavaScript syntax,
  JSON parsing and working-tree diff checks passed.
- The ignored local console remains schema 4 and compatible. No local values,
  device connection, service start, deployment or motion were used.

## Outstanding matters

- The real eight-tag layout, `json_origin_rail_position_mm`, rail axis and sign
  must be measured/confirmed before enabling this for motion-producing tasks.

## Intent to submit

```text
refactor(console): specialize localization for rail offsets
```
