# Baseline grouped drawing executor and blend propagation

- Status: implementation complete; device deployment and L4 motion pending
- Date: 2026-09-08
- Branch: `target/baseline-single-window-runner`
- Source baseline: `ffabdb7ef71aa7857040ef3d8958872d86a21309`
- Goal: propagate `blend_pct` through the PC/MaixCam/RPA2/controller relative-linear primitive and add a guarded PC grouped-plan executor suitable for the single-window Baseline drawing selected by the operator.
- Highest intended validation: L4, but this implementation phase is L1 only. Device publication, service restart, controller import, and physical motion require later explicit gates and factual continuation records.

## Workspace audit

- Worktree `E:\Device Network-baseline-run` was created clean from current `origin/main` for this goal.
- Primary and deployment worktrees contain unrelated user/extension changes and deployment records. They are read-only for this goal.
- The input `E:\Downloads\strokes_band.json` is read-only external task data. Its offline plan currently contains 5 groups, 439 strokes, 3,903 points, 5,220 arm commands, and no chassis reposition barrier.

## Editable scope

- `protocol/motion_link.py`
- `src/console/maixcam_arm_client.py`
- `src/console/runtime_core.py` only if required to expose the new optional field
- `src/maixcam/arm/arm_motion_gateway.py`
- `src/robot_arm/runtime/arm_motion_service.py`
- `tools/robot_arm/build_dobotstudio_project.py` only if generation requires adjustment
- `src/console/drawing/` for a bounded executor
- `app/` for a guarded CLI entry point
- affected tests under `tests/protocol/`, `tests/maixcam/`, `tests/robot_arm/`, `tests/console/`, and `tests/app/`
- `app/README.md`, relevant robot-arm/protocol documentation, this plan, and append-only `plan/log.md`

## Read-only scope and dependencies

- ESP32 runtime and chassis protocol: this selected drawing has no reposition barrier, so the first executor must not connect to, enable, or command the chassis.
- MaixCam video source and configuration.
- Existing ignored device credentials/configuration and all device backups.
- Raw-resource archives `ESP32/`, `Camera/`, and `Robot Arm_Claws/`.

## Required behavior

1. `blend_pct` is optional for compatibility, finite integer 0..100, and reaches controller `RelMovLUser` as `cp`; acceleration and speed remain explicit.
2. Existing callers without `blend_pct` preserve current behavior.
3. Executor accepts only a complete plan with zero reposition barriers and a production-ready drawing configuration.
4. Flatten pen select/return substeps deterministically and execute only the known arm/sleep step kinds.
5. Open one arm session, require a successful preflight PING/STATUS with ready, YOLO mode, motion enabled, valid feedback and no active task, then execute in order.
6. Every arm command must end in `DONE`; explicit rejection/fault or unknown outcome stops all later commands. Never retry a state-changing command.
7. Emit durable progress/checkpoint information without credentials so an interrupted run is observable; do not claim safe automatic resume when terminal position is unsupported.
8. Provide dry-run/summary as the default. Real execution requires explicit CLI admission flags and a production-ready ignored local config.

## Validation plan

- Focused protocol/client/gateway/controller/executor unit tests, including bounds, compatibility, exact `cp`, flattening, preflight rejection, failure stop, and no retry.
- Generate the DobotStudio package and inspect/compile/hash it.
- Plan and dry-run `E:\Downloads\strokes_band.json`; assert no chassis dependency, expected commands, and 12/100/50/20 motion profile.
- Full affected L1 suites, source checks, `git diff --check`, and final status.
- No hardware write or motion in the implementation phase.

## Actual results

- Added optional PC `blend_pct` for relative XYZ motion, strict MaixCam validation at 0..100, an RPA2 `blend_pct` field, and controller mapping to `RelMovLUser` option `cp`. Existing callers default to zero. The upgraded controller also accepts legacy `blend_mm=0` frames for controller-first deployment; nonzero legacy radius remains rejected.
- Added `drawing.executor` and `app/baseline_run.py`. The CLI defaults to dry-run and opens no device connection. Real execution requires an exact canonical job hash, a new exclusive log path, `production_ready=true`, four explicit attended-safety flags, ready YOLO controller status, no active task, matching User/Tool and valid measured feedback.
- Pen select/return recipes flatten deterministically. Every arm request must end in `DONE`; rejection, fault, unknown outcome, timeout, malformed response or disconnect stops later submission without retry. Progress is flushed and fsynced as NDJSON; no automatic resume is exposed.
- The executor accepts only complete plans and never opens a chassis session. Reposition barriers remain rejected for this single-window implementation.
- L1 source check passed for 30 affected Python files. Tests passed: 5 app, 116 applicable console, 58 MaixCam, 19 robot-arm, 28 protocol, and 28 developer-tool tests (254 total). The two existing PySide6 GUI-only console modules were not runnable because PySide6 is absent; all other console tests passed explicitly.
- Generated ignored `build/baseline-ffabdb7-blend-arm-yolo`; source inspection confirms relative-linear blend is parsed at 0..100 and passed as `{"cp": blend}`.
- Real `E:\Downloads\strokes_band.json` dry-run passed: 5 groups, 439 strokes, 3,903 points, 6,135 atomic steps, 5,257 arm commands, 878 waits, and zero chassis commands. All 3,464 draw segments are `speed=12`, `blend=100`, `accel=20`; all 1,333 other relative motions are `speed=50`, `blend=0`, `accel=20`.
- No device file, process, controller project, configuration, or physical state was changed during implementation. No hardware command was sent.
