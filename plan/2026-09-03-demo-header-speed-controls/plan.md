# Editable drawing speed defaults at the top of demo.py

- Status: local implementation and validation complete
- Baseline: 0d84c68, target/pc-json-drawing-demo (synchronized)
- Validation: L0/L1 only; no hardware connection or motion

## Objective and scope

Expose drawing speed, travel/pen speed and acceleration as clearly documented
constants at the beginning of app/demo.py. Retain 15/5/5 percent defaults and
existing command-line overrides. The user will choose any later tuning values;
do not silently increase speed or run another drawing. Also record the user's
confirmation that the preceding hardware test drew the complete picture.

## Workspace audit

The only tracked dirty paths are known user editor settings and the unchanged
prior XYZ diagnostic hunk in plan/log.md. The three untracked XYZ diagnosis,
YZ drawing review and video diagnosis directories are prior-task work. Preserve
all those contents and exclude them from staging. App/test/runtime sources are
clean. Existing authorization permits appending drawing-task log facts; stage
only the new section, never the prior diagnostic hunk.

## Editable scope

- app/demo.py: header constants, DrawingConfig default wiring and clean handling
  of invalid header defaults before IO.
- app/README.md: describe controls, CLI precedence and timing limitations.
- tests/app/test_demo.py: regression tests for defaults/overrides/validation.
- plan/2026-09-03-pc-json-drawing-l3/plan.md: append operator outcome accurately.
- This plan and a new section in plan/log.md.

Read-only: all other files, dataset, config, protocols, device sources and files,
raw archives, previous diagnostics and user editor settings. No dataset, geometry,
point filtering, sleeps, blending, timeout, safety gate or service change.

## Dependencies and risk

The existing command contract accepts integer speed/acceleration percentages
1..100 and serializes primitives with blending disabled. Reuse it unchanged;
PC speed defaults do not remove per-command transport/response latency. No
claim that motor speed is the only or measured dominant source of total delay.
Moving hardware at a new speed requires a new attended safety confirmation;
this task is local UI/configuration ergonomics, not authorization for a faster
real test. The user confirms drawing completeness, not quantified accuracy or
separately verified final pen clearance.

## Validation and commit intent

Test header values propagate to dataclass defaults, CLI defaults and emitted
native options through fake IO; CLI overrides win; invalid defaults fail before
IO. Run all demo tests, supplied-data preview, git diff --check and final git
status. Review/stage only editable files and the added log hunk; commit/push to
the existing drawing branch/PR without merging or changing other work.

## Actual results

- Added DRAW_SPEED_PCT, TRAVEL_SPEED_PCT and ACCEL_PCT in the file header,
  retaining 15/5/5. DrawingConfig reads them as defaults; CLI overrides remain.
- Travel covers joint home, first-point positioning and pen-down/up. Documented
  integer percent units and retained per-segment latency/blending limitations.
- Added three regressions for header-to-CLI/native propagation, CLI precedence
  and clean invalid-default rejection before IO. All 19 demo tests passed.
- Supplied-file preview passed with unchanged 4 strokes / 269 points / 282
  commands and 15/5/5 defaults. git diff --check passed; no hardware action.
- Recorded the user's complete-picture confirmation in the L3 plan, without
  inventing a numerical accuracy or separate physical pen-clearance result.
- Commit intent: feat(app): expose drawing speed controls in demo header.
  Push only this scoped change to the existing branch; preserve unrelated edits.
