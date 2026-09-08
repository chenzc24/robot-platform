# Build a Localized Baseline coordinate rehearsal simulator

- Status: completed
- Responsible: joint
- Highest validation level: L1

## Objective

Create a no-device simulation system for the single production candidate
`localized_baseline`. It must rehearse the exact current chain:

```text
normalized drawing points -> fixed User-Y/Z mapping -> one-axis JSON offset
-> reachable drawing window -> safe reposition barrier -> idealized direct rail
move -> STOP/enabled_stopped -> new localization generation -> checkpoint resume
```

The simulator is not a 3-D camera/base/tool transform and must not claim physical
calibration, measured stop, reachability, collision clearance or real motion.

## Initial workspace audit

- `main` is clean and synchronized with `origin/main` at `7da29e1`.
- `app/localized_baseline_run.py`, the drawing loader/planner/coordinator and the
  one-dimensional localization contract are the current production lineage.
- `dataset/dobot-generation-1.json` is present locally and validates as 439
  strokes / 3,903 points. With the example geometry and zero offset it fits one
  configured User-Y window, so a narrower explicitly simulated reach interval
  is needed to exercise repositioning before hardware use.
- No device connection, deployment or hardware state is required or authorized.

## Editable scope

- `src/console/drawing/simulator.py`
- `src/console/drawing/__init__.py`
- `app/localized_baseline_sim.py`
- `app/localized-baseline-simulator.html`
- `tests/console/test_localized_baseline_simulator.py`
- `tests/app/test_localized_baseline_sim.py`
- `docs/console/localized-baseline-simulator.md`
- `app/README.md`, `README.md`, `docs/overall-plan.md`,
  `docs/console/drawing-control-modes.md`
- `config/drawing-control.example.json`
- this plan and append-only `plan/log.md`

## Read-only scope and shared dependencies

- Production loader, planner, coordinator, executor, localization state machine,
  device clients, protocol and deployed device sources.
- `dataset/` and ignored local configuration are input data only.
- `ESP32/`, `Camera/`, and `Robot Arm_Claws/` remain protected raw archives.
- Current architecture and device responsibility boundaries remain unchanged.

## Intended implementation

1. Reuse the production drawing loader and `build_drawing_plan`; do not duplicate
   the window/checkpoint decision logic.
2. Add a deterministic ideal-localization scenario driver. At every barrier it
   converts the planner's suggested JSON-offset delta into a simulated rail move,
   requires the logical STOP/enabled-stopped sequence, increments localization
   generation, and replans from the exact checkpoint.
3. Emit a self-contained HTML rehearsal with a User-Y/Z canvas, reachable band,
   logical drawing, selected window, rail/reference markers, coordinate probe,
   window trace and explicit simulation limitations.
4. Provide a CLI that defaults to no device access and writes only the requested
   report path. Support explicit simulated reach overrides to force a multi-window
   rehearsal without changing production configuration.

## Risks and safety constraints

- A visually successful simulation is not permission for L2/L3/L4 operation.
- The simulated rail movement and relocalization are idealized; no slip, stop
  distance, image noise, tag dropout, latency, yaw or calibration error is added
  unless a future bounded goal models it explicitly.
- `enabled_stopped` is represented only as the existing logical state, never as
  measured physical standstill.
- Simulation overrides must be labeled and must not write production/local device
  configuration.

## Validation plan

- Unit tests for coordinate equations, sign/scale, exact checkpoint progress,
  generation increments, multi-window completion and invalid/no-progress cases.
- CLI test proving no runtime/device factory is loaded and the report is
  self-contained.
- Run the 439-stroke real dataset with the example drawing configuration and a
  deliberately narrow simulated User-Y interval; inspect the generated report.
- Run all existing L1 test groups, source compilation, JSON checks,
  `git diff --check`, full diff review and final Git status.

## Commit intent

Commit and push the bounded simulator, tests, documentation, plan and factual log
directly to the sole `main` branch after L1 validation.

## Actual results

- Added a pure simulation driver that reuses the production loader and planner.
  It calculates offset from `(r-r0)`, obeys exact planner checkpoints, derives
  ideal direct rail moves from the planner's requested offset, requires the
  safe-home / logical-stop sequence, increments localization generation and
  rejects missing safe-home, invalid scale/reach and no-progress/window-limit
  cases.
- Added a no-device CLI and self-contained interactive HTML report. The report
  shows the User0 Y/Z mapping, reachable band, completed/current/pending and
  unreachable segments, coordinate probe, rail positions, safe-barrier phases,
  checkpoint table, total travel and direction-reversal warnings. It contains
  no network fetches and the CLI imports no runtime or device factories.
- Updated the safe example and operating documentation so normal production
  operation exposes only `localized_baseline`; Baseline remains an internal
  open-loop diagnostic and Advanced remains a future strategy. Device deployment
  and responsibility boundaries are unchanged.
- Rehearsed `dataset/dobot-generation-1.json` with the checked-in example drawing
  geometry and an explicit simulated User-Y interval of `[-60,60]` mm. The 439
  strokes / 3,903 points completed in three windows: 1,464, 950 and 1,489 planned
  points, with checkpoints at group 2 and group 3 boundaries and generations
  1, 2 and 3.
- The ideal scenario moved the rail from `0` to `-67.6362` mm and then reversed
  to `+35.25555` mm. Final JSON offset was `-35.25555` mm; total absolute travel
  was `170.52795` mm. This reversal is caused by the deliberately narrow exercise
  reach plus current group order and is recorded as a review signal, not a claim
  about the unmeasured hardware reach.
- Focused simulator/CLI tests passed 6/6. The full repository suite passed 375
  tests. Python compilation, example JSON parsing, generated-report JavaScript
  syntax, self-contained/no-fetch checks and `git diff --check` passed.
- Browser automation refused local-file navigation, so visual browser QA was not
  performed by the agent. The report structure, embedded data, JavaScript syntax
  and interactions are covered by static/unit checks; the generated report is
  left for operator inspection before tomorrow's hardware session.
- No runtime configuration, device connection, deployment, service action,
  chassis command, arm command or motion occurred. L2/L3/L4 were not run.
