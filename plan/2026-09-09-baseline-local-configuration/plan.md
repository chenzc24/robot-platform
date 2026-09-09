# Baseline local configuration

- Status: completed
- Responsible: joint
- Highest validation level: L1

## Objective

Create the ignored PC-side drawing configuration for the confirmed 700 x 200 mm
canvas and Baseline relocation mapping, using initial JSON-axis offset 0 mm and
`json_mm_per_rail_mm = -1.0`, without connecting to or moving hardware.

## Initial state of the workspace

`main` is synchronized with `origin/main` at `7022de5`. The workspace already
contains an unrelated user change in `.vscode/settings.json` and the separate
in-progress `plan/2026-09-09-esp32-positive-vx-direction-test/` record. Neither
is owned or modified by this goal.

## Modifyable File

- `config/drawing.local.json` (ignored local configuration)
- `config/drawing-control.local.json` (ignored local configuration)
- `plan/2026-09-09-baseline-local-configuration/plan.md`
- append-only entry in `plan/log.md`

## Read-only files and directories

- `.vscode/settings.json`
- `plan/2026-09-09-esp32-positive-vx-direction-test/`
- `config/*.example.json`
- `build/drawing-d2469eb/`
- all device filesystems and raw-resource archives

## Shared Dependencies

- Drawing geometry schema and loader in `src/console/drawing/`
- Baseline relocation contract in `docs/console/drawing-control-modes.md`
- Frozen d2469eb Baseline configuration template

## Risk and safety door

- Risk: local runtime admission configuration; incorrect values could cause
  wrong open-loop displacement if later armed for execution
- Hardware: none
- User operations: none
- Backup and recovery: delete or replace the two ignored local files from the
  committed examples; no device state changes
- Motion gate: not applicable because this goal performs only local parsing and
  simulation/dry-run checks and keeps both `production_ready` flags false

## Expected work

1. Write the 700 x 200 mm drawing geometry local configuration.
2. Write Baseline selection with offset 0 mm and scale -1.0 mm/mm.
3. Parse both files and run a repository sample dry-run without device access.

## Validation

- Load both local files through their production parsers.
- Run the unified drawing entry point in default dry-run mode on the real
  repository sample.
- `git diff --check`
- `git status --short --branch`

## Actual results

- Created both ignored local configurations. Drawing geometry is 700 x 200 mm,
  User-Y offset is -350 mm, User-Z offset is -133.333333333 mm, and the retained
  User-Y reach window is `[-200,180]` mm.
- Selected `baseline`, with initial JSON-axis offset 0 mm and
  `json_mm_per_rail_mm = -1.0`. Both production-ready flags remain false.
- Both files passed their production parsers. The unified runner dry-run parsed
  the repository's real `dataset/dobot-generation-1.json` sample as 439 strokes
  and 3,903 points, without opening any device connection or causing motion.
- `git diff --check` passed. Final scoped status contains only this tracked plan
  and the two expected ignored local configuration files.

## Outstanding matters

- Baseline remains unarmed until its separate physical direction observation
  and current attended motion gate are complete.

## Experience signal (for manual review)


## Intent to submit

```text
docs: record baseline local configuration
```
