# Integrate physical rehearsal with production relocation logic

- Status: completed
- Responsible: joint
- Highest validation level: L1

## Objective

Make the Localized Baseline rehearsal execute the same production coordinator,
drawing-window executor and `LocalizedBaselineRelocator` used by
`app/run_drawing.py`. Keep only deterministic arm, chassis, localization and
clock adapters in the simulator so the rehearsal cannot drift from the real
`VELOCITY -> STOP -> STATUS -> fresh AprilTag -> checkpoint resume` code path.

The inherited colleague-tested User0-Y drawing window remains configured as
`[-200,180]` mm. X/Z, joint, collision and moving-arm envelope analysis are
explicitly outside this goal at the user's direction.

## Initial audit

- `main` is clean and synchronized with `origin/main` at `488d0ce`.
- Production movement is implemented in `src/console/drawing/control_modes.py`
  and orchestration in `src/console/drawing/coordinator.py`.
- The current rehearsal reuses the production planner but independently copies
  the relocation sequence and offset update. That duplication is the target.
- No local drawing or drawing-control production configuration exists; tracked
  examples remain `production_ready=false`.

## Editable scope

- `src/console/drawing/simulator.py`
- `app/localized_baseline_sim.py`
- `app/localized-baseline-simulator.html`
- `tests/console/test_localized_baseline_simulator.py`
- `tests/app/test_localized_baseline_sim.py`
- `docs/console/localized-baseline-simulator.md`
- this plan and append-only `plan/log.md`

## Read-only scope and shared dependencies

- Production coordinator, planner, executor and relocation implementation are
  read-only dependencies for this goal.
- `src/esp32/`, `src/maixcam/`, `src/robot_arm/`, `protocol/`, local device
  configuration and all device filesystems are read-only.
- `ESP32/`, `Camera/`, `Robot Arm_Claws/` remain protected raw archives.

## Expected work

1. Load the tracked drawing-control model in the rehearsal CLI.
2. Implement deterministic fake arm/chassis/localization/clock adapters.
3. Drive `execute_drawing` end to end and derive the visual report from its
   production events and command evidence.
4. Retain fixed gain, stop overshoot, localization-error and rail-bound failure
   scenarios without substituting planner targets for measurements.
5. Prove production relocation methods were invoked and that zero progress,
   bounds and stale localization still fail.

## Validation

- Focused simulator and CLI tests.
- Production drawing/coordinator/control-mode regression tests.
- Python compilation and generated-report JavaScript syntax.
- Configuration-faithful and fixed physical-stress rehearsals on the 439-stroke
  dataset.
- Full repository L1 discovery, `git diff --check`, scoped diff and status audit.

## Safety

- L1 only: no hardware discovery, connection, command, deployment, service
  action, configuration write or motion.
- The simulated adapters contain no network or device factory imports.
- Real L3/L4 execution remains separately gated by `AGENTS.md` and the guarded
  production runner.

## Commit intent

Commit and push the bounded integration directly to the sole `main` branch
after validation.

## Actual results

- Replaced the rehearsal's copied relocation loop with the production
  `execute_drawing` coordinator, `execute_drawing_window` arm executor and
  `LocalizedBaselineRelocator`. Production planner/coordinator/control-mode
  sources remained unchanged.
- Added deterministic fake arm, chassis, localization and clock adapters. The
  chassis integrates the real production timed `VELOCITY` calls before applying
  fixed motion gain and stop overshoot; the localization adapter exposes the
  resulting position only through a newer measured generation after production
  `STOP` and parsed `enabled_stopped`.
- The CLI now loads `drawing-control.example.json`, so speed, refresh, hold,
  maximum distance, scale and localization timing are shared with the actual
  runner. Tracked `production_ready=false` is enabled only inside the isolated
  simulation object and no local or device configuration is changed.
- The colleague-tested `[-200,180]` mm User0-Y window completed the 439-stroke /
  3,903-point dataset in one window with no relocation. The fixed narrow-window
  stress scenario retained three windows and two relocations, commanded
  `167.550502` mm, simulated true travel `163.84848192` mm and one reversal.
  Its production-path evidence recorded 35 `VELOCITY` refreshes, two `STOP`s,
  two parsed status checks, two relocalization requests and 5,270 arm actions.
- Focused simulator, CLI, production control-mode, coordinator and executor
  tests passed. All 385 repository tests passed: app 13, console 163,
  development 28, ESP32 76, MaixCam 58, protocol 28 and robot arm 19. Python
  compilation, both generated-report JavaScript checks and `git diff --check`
  also passed.
- No hardware discovery, connection, command, configuration write, deployment,
  service action or motion occurred.
