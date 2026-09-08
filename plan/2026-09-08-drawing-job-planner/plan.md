# Offline grouped drawing importer and planner

- Status: `completed`
- Responsible: `agent`
- Highest validation level: `L1`

## Objective

Implement Goal A of the reviewed first-generation Dobot migration: safely read
the delivered controller project without executing `var.py`, emit canonical
JSON into an explicitly selected local path, validate grouped or StrokeReview
stroke documents, convert normalized points to configured User Y/Z millimetres,
and produce a deterministic preview/checkpoint plan with no device imports or
connections.

## Initial state of the workspace

The primary worktree remains dirty and behind current remote main:

```text
## main...origin/main [behind 5]
 M .vscode/settings.json
 M app/demo.py
 M plan/log.md
?? pelican-bicycle.svg
?? plan/2026-09-03-arm-xyz-singularity-diagnosis/
?? plan/2026-09-03-arm-yz-drawing-review/
?? plan/2026-09-03-video-stream-diagnosis/
?? plan/2026-09-08-arm-project-pc-migration/
```

All listed paths belong to prior/user work. This goal uses a clean isolated
worktree based on `origin/main`:

```text
## target/drawing-job-planner...origin/main
```

## Modifiable files

- `.gitignore` (one explicit local drawing-config rule)
- `src/console/drawing/` (new offline package)
- `app/drawing_task.py` (new preview-only entry point)
- `app/README.md`
- `tools/dev/import_dobot_drawing.py` (new safe converter)
- `config/drawing.example.json` (non-production placeholders/defaults)
- `tests/console/test_drawing_job.py`
- `tests/app/test_drawing_task.py`
- `tests/dev/test_import_dobot_drawing.py`
- `docs/robot-arm/pc-drawing-task.md`
- `plan/2026-09-08-drawing-job-planner/plan.md`
- `plan/log.md` (append only after completed validation)

## Read-only files and directories

- `E:\Downloads\机械臂代码——1代.zip`
- `ESP32/`, `Camera/`, `Robot Arm_Claws/`, `tmp/`
- `app/demo.py` and its uncommitted primary-worktree speed change
- `protocol/`, `src/maixcam/`, existing `src/console/` modules
- device files, local console settings and taught controller points

## Shared Dependencies

- StrokeReview version-1.0 normalized axis/canvas/stroke fields
- Existing one-dimensional localization convention: scalar JSON-axis offset in
  millimetres before conversion to an arm command
- Existing arm primitive names are documentation only in this goal; the planner
  must not import or instantiate `MaixCamArmClient`
- Archive SHA-256
  `f7a7d1856690d2858d5618a98c551b8efd368e3a7f78d36b8e2bb0fc6a8c79c7`

## Risk and safety door

- Risk: offline software that will later feed a moving arm. Incorrect geometry,
  group mapping or checkpoint placement could become hazardous if consumed
  without later admission checks.
- Hardware: none.
- User operations: none.
- Backup and recovery: isolated Git branch; source archive is read-only.
- Motion gate: not applicable to L1. This goal contains no execute option,
  endpoint configuration, device client import, network access or motion call.

## Expected work

1. Parse a unique `var.py` from a ZIP or project directory with `ast.parse` and
   `ast.literal_eval`; reject every non-literal or additional statement.
2. Validate five-group legacy jobs and flat StrokeReview jobs into immutable
   internal models, preserving stroke/group order and point values.
3. Load an explicit local geometry/group configuration and produce an offline
   plan containing abstract pen changes, home/sleep/relative-move steps and a
   pre-motion reposition barrier/checkpoint when a planned User-Y endpoint lies
   outside the configured range.
4. Add a preview-first CLI that prints hashes, counts, bounds and command counts
   and can write a deterministic plan JSON, but cannot execute it.
5. Cover archive-scale facts and malicious/ambiguous inputs with deterministic
   tests and document unresolved physical assumptions.

## Validation

- Focused unit tests for importer, model/planner and CLI
- Full console/app/dev Python suites as applicable
- Repository Python source checker for changed Python paths
- JSON parse of the configuration example
- Preview/import of the supplied ZIP to ignored temporary paths only
- `git diff --check`
- staged file/secret/data audit
- `git status --short --branch`

L1 proves parsing, normalization, mapping, coordinate arithmetic, pre-motion
barriers, checkpoints and absence of a device execution surface. It does not
prove taught points, User/Tool frames, reachability, collision freedom, pen
geometry, chassis movement or drawing accuracy.

## Actual results

- The supplied archive was read without importing or executing its Python. Its
  SHA-256 matched the audited value. The importer produced an ignored canonical
  `dataset/dobot-generation-1.json` containing 5 groups, 439 strokes and 3,903
  points. The canonical drawing hash is
  `dd78bd83f4553881b9c9c841b860c61699e16b99b668783b70c5fc7339d13da7`;
  the pretty-printed local file hash is
  `346fa815f405b5426624d7ce8d4b242614d98f785b14d23659a506b6a0718421`.
- With an audit-only in-memory mapping for all five group names and the explicit
  placeholder geometry, planning completed with 439 strokes, 3,903 points,
  5,220 arm primitives, 5 pen selections and no reposition barrier. The example
  config intentionally rejected this drawing because its physical pen mappings
  are not yet known.
- L1 regression passed 307 tests: 22 app, 99 applicable console, 28 developer,
  55 ESP32, 57 MaixCam, 28 protocol and 18 robot-arm tests. The two existing
  console GUI modules were not run because this worktree's Python environment
  does not contain PySide6. A repository-root discovery command found zero
  tests due to the existing test-directory layout and is not counted as a pass.
- The repository Python source checker passed all 7 changed Python source files.
  The example JSON parsed, the changed source contained no device-client or
  connection import, and the focused importer/planner/CLI tests passed.
- No hardware connection, service start, deployment, device write or motion
  occurred. The primary worktree's prior dirty files were not modified or
  staged; only the ignored converted dataset was also written there for the
  user's local follow-up.

## Outstanding matters

- Physical/color semantics remain those listed in the master migration plan in
  the primary worktree; no value was inferred in this goal.
- Pen-rack poses and group-to-pen mapping, taught home pose, User/Tool frames,
  reachable range, pen travel, DI wait semantics and the archive's 210 mm versus
  runtime 150 mm canvas discrepancy require physical confirmation.
- The current MaixCam arm protocol has no buffered-path blend or digital-input
  wait primitive. A later reviewed goal must add executor/state-machine admission
  gates and measure performance before any L3/L4 motion test.

## Experience signal (for manual review)


## Intent to submit

```text
feat(console): add offline grouped drawing planner
```
