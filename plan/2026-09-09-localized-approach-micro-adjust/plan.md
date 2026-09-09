# Localized Baseline reserved approach and AprilTag micro-adjustment

- Status: completed
- Responsible: agent
- Highest validation level: L1

## Objective

Keep the confirmed Home-relative drawing range unchanged.  For
`localized_baseline`, replace one-shot movement to the planner's full centering
suggestion with a bounded normal window target, a deliberately short coarse
approach, and AprilTag-measured, bounded micro-adjustment before checkpoint
resume.

## Initial workspace audit

- Current `main` contains the completed queued-stroke work at `69ecd3a`; it is
  one commit ahead of `origin/main`.
- `.vscode/settings.json` is an unrelated user change and is read-only.
- The preceding joint goal is complete and committed. Its drawing, simulator,
  protocol and test modifications are the baseline for this goal; do not
  overwrite or redesign its queue protocol.
- No device, local configuration, device filesystem, raw-resource archive or
  live service may be touched.

## Editable scope

- `src/console/drawing/control_modes.py`
- `src/console/drawing/simulator.py`
- `src/console/runtime_core.py` and `src/console/web_console/runtime.py`, only
  to route the already-committed `draw_stroke` arm-client operation through the
  existing Web drawing adapter
- directly related drawing control, simulator and coordinator tests
- `config/drawing-control.example.json`
- `docs/console/drawing-control-modes.md`
- `docs/console/localized-baseline-simulator.md`
- this plan and append-only `plan/log.md`

## Read-only scope and dependencies

- geometry/range configuration and ignored local configuration
- drawing job data, planner hard-boundary contract, executor queue protocol,
  device clients, device services and raw-resource archives
- shared checkpoint/reposition payloads, chassis STOP/status contract and
  AprilTag localization state-machine generation contract

The queued-stroke implementation committed immediately before this goal exposed
one Web-adapter omission during this goal's regression run: it does not change
the queue protocol, but the Web runtime must forward its existing client method
for the Drawing tab to remain a valid execution route.

## Design and safety invariants

- The hard arm drawing boundary is unchanged and is still the first barrier.
- Baseline and Advanced semantics remain unchanged.
- Localized Baseline targets at most a configured normal window advance; it
  performs a shorter coarse move, obtains a fresh AprilTag lock, then makes
  finite, bounded direct micro-moves with a fresh STOP/status/lock after each.
- A resumed drawing plan uses only the final measured offset; no commanded or
  inferred position is substituted for AprilTag measurement.
- Failure, exhausted attempts, stale/missing lock, invalid status or no useful
  residual progress raises an error before another drawing window is executed.
- Only local fakes and simulation are used for validation.

## Planned validation

- configuration schema and backwards-compatibility tests
- relocator tests for 160 mm target cap, 140 mm coarse approach, repeated fresh
  generations, residual tolerance, bounded attempts and error paths
- coordinator/checkpoint tests proving final offset is measured
- deterministic production-path Localized Baseline simulation of the repository
  439-stroke sample, including non-ideal movement/localization samples
- Python compilation, JSON parse, `git diff --check`, scoped status and staged
  secret review

## Actual results

- Added schema 3 settings for a 160 mm maximum normal window target, 20 mm
  coarse-approach reserve, 20 mm maximum micro step, 3 mm measured tolerance
  and three bounded micro-adjust attempts. Schema 2 remains accepted and gains
  the same conservative defaults, so the ignored current local configuration
  is protected without being edited.
- Localized Baseline now caps a planner center request before movement. For a
  180 mm request at scale -1, tests prove a 160 mm target executes as a 140 mm
  coarse move followed by a 20 mm correction, with STOP/status/new AprilTag
  generation after each physical command. Only the final measured offset is
  returned to the coordinator.
- No progress, attempt exhaustion, stale pre-move offset and normal stop/status
  failures reject before another drawing window. Baseline and Advanced behavior
  are unchanged.
- Updated the production-path simulator to record every coarse/micro move in a
  relocation and added the existing staged-stroke arm operation to the Web
  drawing adapter. This was required to keep the already committed Drawing tab
  integration executable after the queue protocol changed.
- L1 passed 68 focused tests, Python compilation and control JSON parsing.
  The real repository 439-stroke / 3,903-point rehearsal completed with 15
  windows and 14 relocations under motion gain 0.96, 1.5 mm stop overshoot and
  a repeated 0.4 mm localization error. It used 2,287.6 mm commanded / 2,259.096
  mm simulated actual rail travel, final AprilTag generation 43, and no device
  configuration, connection, command, service action or motion.

## Outstanding matters

- The numerical reserve, tolerance and step defaults are conservative design
  values, not physical calibration. A separately authorized attended L3/L4
  validation must measure real stop residual and AprilTag repeatability before
  enabling hardware execution.

## Intent to submit

```text
feat(drawing): approach localized windows with micro-adjustment
```
