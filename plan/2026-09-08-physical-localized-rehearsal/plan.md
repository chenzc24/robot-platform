# Rehearse Localized Baseline with an independent physical-error model

- Status: completed
- Responsible: joint
- Highest validation level: L1

## Objective

Replace the simulator's completion-oriented perfect-move assumption with a
strictly separated physical rehearsal model, then visibly step through one
configuration-faithful run and one fixed-parameter stress run.

The model must distinguish:

```text
planner requested JSON delta
-> commanded open-loop rail displacement
-> independently simulated true rail displacement
-> STOP / logical enabled_stopped
-> AprilTag measured rail position
-> measured delta from the measured reference r0
-> JSON offset used for checkpoint replanning
```

It must be allowed to require extra relocations or fail; it must never set the
measurement directly to the planner's desired offset merely to finish drawing.

## Initial audit

- `main` is clean and synchronized at `35069fd`.
- The current simulator explicitly assumes perfect relocation at the planner's
  suggested offset. That is valid for a pure coordinate-chain check but is not a
  physical rehearsal.
- Production planner, runtime/device code, protocol and device deployment remain
  read-only. No hardware action is authorized.

## Editable scope

- `src/console/drawing/simulator.py`
- `app/localized_baseline_sim.py`
- `app/localized-baseline-simulator.html`
- `tests/console/test_localized_baseline_simulator.py`
- `tests/app/test_localized_baseline_sim.py`
- `docs/console/localized-baseline-simulator.md`
- this plan and append-only `plan/log.md`

## Physical scenario inputs

- Fixed User-Y reach interval, independent of the drawing.
- Fixed motion gain and signed stop error applied to every commanded rail move.
- A predetermined sequence of AprilTag measurement errors, including the
  reference measurement, independent of planner output.
- Fixed rail travel bounds. Exceeding them terminates the rehearsal instead of
  forcing completion.

No random values are used; the scenario is repeatable and auditable.

## Validation

- Prove a perfect scenario still matches the old coordinate result.
- Prove motion gain/stop error alter true rail position independently.
- Prove localization error changes measured offset and can cause an additional
  relocation or terminal failure.
- Prove fixed rail bounds and a non-progressing physical move stop the rehearsal.
- Run the current real dataset first with its configured reach unchanged, then
  a fixed stress scenario not derived from its geometry.
- Generate and visibly inspect the report, step through every window, verify
  changing rail/offset/generation/probe state, run all repository tests, compile
  sources, validate generated JavaScript and run Git diff/status checks.

## Safety and interpretation

- L1 only. No device configuration, connection, command, deployment or motion.
- The model is one-dimensional and does not add yaw, collision, kinematics,
  camera projection or physical-stop proof.
- The stress scenario is not calibration data and must not be copied to a local
  production configuration.

## Commit intent

Commit and push the bounded simulator correction and factual record directly to
the sole `main` branch after validation.

## Actual results

- Replaced the former exact-target relocation assumption with independently
  calculated commanded, true and measured rail states. Replanning now uses only
  the measured delta from the separately measured reference position.
- The configuration-faithful 439-stroke / 3,903-point dataset completed in one
  window with no chassis relocation because the configured User-Y reach is
  `[-200,180]` mm. This is the honest current-config result.
- A separate fixed stress scenario used User-Y `[-60,60]` mm, motion gain
  `0.96`, signed stop overshoot `1.5` mm, declared AprilTag errors and rail
  bounds `[-150,150]` mm. It completed in three windows after two relocations.
  Commanded absolute travel was `167.550502` mm while independently calculated
  true travel was `163.84848192` mm. Final true rail position was
  `32.33097792` mm, measured position `31.73097792` mm and measured JSON-axis
  offset `-31.33097792` mm. The route reversed once.
- Failure tests prove zero physical progress and rail-bound violations terminate
  the rehearsal. Measurements are never replaced with the planner target.
- L1 passed 5 focused simulator tests, 3 focused simulator CLI tests, Python
  compilation, both generated-report JavaScript checks, inline visualization
  rendering/syntax, `git diff --check`, and all 383 repository tests discovered
  across app, console, dev, ESP32, MaixCam, protocol and robot-arm suites.
- No hardware connection, configuration write, deployment, service action or
  motion occurred. Browser file-URL automation remained disallowed; the report
  is instead exposed as an inline interactive visualization and standalone
  self-contained HTML artifacts.
- During implementation, the separate
  `2026-09-08-unified-image-drawing-runner` goal created unrelated dirty paths.
  They were audited, preserved and excluded from this goal's staging.
