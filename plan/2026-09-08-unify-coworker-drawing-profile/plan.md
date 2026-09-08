# Unify drawing modes on the coworker controller profile

- Status: `completed`
- Responsible: `agent`
- Highest validation level: `L1`

## Objective

Remove the obsolete standalone `app/demo.py` path and make the single grouped
drawing planner/configuration the source for both Baseline and Advanced modes.
Represent the explicit motion parameters from
`E:\Downloads\机械臂代码——1代.zip` without replacing omitted controller options
with invented percentages.

## Initial state and source evidence

- Clean worktree `E:\Device Network-deploy-baseline`, branch
  `target/unify-coworker-drawing-profile`, based on remote `main` at `12c84cc`.
- The ZIP is read-only input. Its recorded SHA-256 is
  `f7a7d1856690d2858d5618a98c551b8efd368e3a7f78d36b8e2bb0fc6a8c79c7`.
- Its in-stroke call explicitly uses `v=12, cp=100`. Home, anchor, pen,
  rack and gripper moves omit speed/acceleration options and therefore use the
  controller project's defaults.
- The primary worktree has an unrelated uncommitted `app/demo.py` 60% edit and
  other dirty files. It remains untouched; deleting the tracked file on this
  branch does not overwrite that working copy.

## Modifiable scope

- delete `app/demo.py` and `tests/app/test_demo.py`
- rewrite `app/README.md` and update direct documentation links/references
- `config/drawing.example.json`
- `src/console/drawing/config.py`, `planner.py`, and directly related tests
- dated deployment candidate documentation/manifest if affected
- this plan and append-only `plan/log.md`

## Read-only scope

- ESP32, MaixCam and robot-arm runtime/protocol code
- localization and relocation strategy implementation
- device-local configuration, generated build output, devices and raw archives

## Design

- Baseline and Advanced share the same drawing job, planner and drawing config;
  only their chassis relocation strategies differ.
- Add explicit `draw_blend_pct=100` and retain `draw_speed_pct=12`.
- Represent omitted source travel speed and acceleration as JSON `null` and
  omit those options from abstract planner steps. Do not reinterpret controller
  defaults as 5%.
- Preserve all other delivered geometry, P1-P4, rack and gripper values.
- This goal represents the source semantics in the PC plan. The current arm
  gateway still requires explicit speed/acceleration and forces blending zero;
  enabling exact execution requires a separate reviewed cross-device contract
  change or bounded stroke executor. Do not claim runtime parity here.

## Validation and safety

- L1 only: ZIP hash/read-only parameter audit, drawing/config/app regressions,
  preview inspection, source/JSON/diff/staged-scope checks.
- No device connection, upload, import, service action, configuration write or
  motion.

## Actual results

- Deleted the standalone `app/demo.py` and its dedicated tests. Updated the app
  and root entry points so grouped drawing is the only current PC drawing path.
- Added `draw_blend_pct=100`, retained `draw_speed_pct=12`, and changed source-
  unspecified travel speed/acceleration to `null`. Abstract draw steps carry
  exactly speed 12 and blend 100; all non-draw motion steps omit speed,
  acceleration and blend options.
- Both Baseline and Advanced already consume the same grouped planner. No
  relocation strategy now owns a separate arm parameter set.
- The supplied ZIP SHA-256 matched its recorded value. A real 5-group,
  439-stroke, 3,903-point preview completed with 5,220 arm primitives; 3,464
  draw segments carried 12/100 and 1,342 other motion steps carried no invented
  option.
- L1 passed 23 focused and 189 applicable regression tests: app 3, console 111,
  MaixCam 57 and robot arm 18. The 9-path source check, example/local JSON parse
  and `git diff --check` passed.
- Created ignored `config/drawing.local.json` and
  `config/drawing-control.local.json` in the deployment worktree with production
  gates false and Baseline selected. They contain no credentials.
- No protocol/device runtime was changed. The current arm gateway still cannot
  execute omitted controller defaults or `cp=100`; full runtime parity remains
  a separate cross-device implementation and validation goal.
- No device connection, upload, import, reset, service action, configuration
  write to hardware or movement occurred.

## Intent to submit

```text
refactor(drawing): unify modes on coworker motion profile
```

Implementation commit `2e6a388` was merged through PR #12 into `main` as
`8028f4e`. No deployment or hardware operation was performed.
