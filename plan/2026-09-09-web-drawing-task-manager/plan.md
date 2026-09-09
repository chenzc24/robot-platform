# Web drawing task manager and mode switching

- Status: completed
- Responsible: agent
- Highest validation level: L1

## Objective

Integrate the existing three drawing strategies into the localhost Web console
as one backend-owned task with explicit prepare/start/cancel lifecycle, immutable
mode selection during execution and exclusive ownership of the arm and chassis.
Do not connect to, configure or move real hardware.

## Initial state of the workspace

The workspace is intentionally dirty because another operator session is
performing the full Baseline CLI goal. Its changes to
`src/console/maixcam_arm_client.py`, its focused test,
`docs/console/drawing-control-modes.md`, ignored local configurations and
`plan/2026-09-09-full-baseline-439-strokes/` are read-only for this goal.
`.vscode/settings.json` is also an unrelated user change. This goal will not
switch branches, restart the Web console, touch local runtime configuration or
invoke any device-facing command.

## Modifyable File

- `src/console/web_console/`
- `config/drawing-web.example.json`
- `config/drawing-web.local.json` (ignored, default-deny local policy)
- `.gitignore` (drawing Web local policy only)
- Web-console-focused tests under `tests/console/`
- `docs/console/control-console-ui.md`
- `plan/2026-09-09-web-drawing-task-manager/plan.md`
- append-only `plan/log.md`

## Read-only files and directories

- `.vscode/settings.json`
- `app/`
- `src/console/maixcam_arm_client.py`
- `src/console/drawing/config.py`
- `tests/console/test_maixcam_arm_client.py`
- `docs/console/drawing-control-modes.md`
- `plan/2026-09-09-full-baseline-439-strokes/`
- `config/*.local.json`, `logs/`, device filesystems and raw-resource archives

## Shared Dependencies

- Existing drawing configuration, planner, coordinator, executor and strategy
  implementations under `src/console/drawing/`
- Existing Web-console arm/chassis sessions, I/O locks and localization state
  machine
- Existing `GET /api/state` snapshot contract

## Risk and safety door

- Risk: cross-device runtime arbitration and task admission logic. Incorrect
  ownership could allow manual and automatic commands to interleave.
- Hardware: none for this goal
- User operations: the user's other CLI session remains untouched
- Backup and recovery: revert only this goal's scoped tracked files
- Motion gate: not applicable; only fake-client unit tests and static checks are
  permitted. No live server launch or hardware connection is allowed.

## Expected work

1. Add a Web-backend drawing task manager that prepares an immutable mode/job
   snapshot and executes it on a worker using the runtime-owned sessions.
2. Add API lifecycle actions and state, reject manual control while a drawing
   task owns the devices, and retain STOP/cancel access.
3. Add mode-specific readiness, switching and arbitration tests plus a minimal
   UI task panel.
4. Document the lifecycle and mode-switching rules.

## Validation

- Focused Web console and drawing-task unit tests using fakes only
- Existing Web console test suite and JavaScript syntax test
- Python compilation for changed modules
- `git diff --check`
- `git status --short --branch`

## Actual results

- Added one `POST /api/drawing/task` route with `prepare`, `start` and `cancel`
  actions. Existing `GET /api/state` now publishes sanitized drawing lifecycle,
  immutable task/mode/hash, readiness, progress, result and log-path state.
- Added a backend `DrawingTaskManager` with allowlisted JSON jobs, exact hashes,
  independent per-mode release gates, current attended confirmations, durable
  JSONL logs, asynchronous execution and cancellation-aware waits.
- Added one cross-device `control_owner`. Drawing execution reuses the existing
  Web runtime sessions and I/O locks; manual connect, enable/disable, chassis
  motion, arm connect/disconnect and arm motion fail closed while a drawing task
  owns the routes. STOP/cancel remains available and finalization attempts
  chassis STOP/DISABLE before releasing ownership.
- Mode changes are accepted only by preparing a new immutable task while not
  running/stopping. No hot switch, fallback or cross-mode checkpoint reuse was
  added. Baseline needs no localization; the other two modes require complete
  matching runtime localization prerequisites.
- Added the Drawing UI tab and default-deny local Web policy. The real repository
  sample prepared locally as 439 strokes / 3,903 points with all release gates
  false. The Web backend was not restarted.
- L1 passed Python compilation, JSON parsing, 16 Web API tests, 11 new drawing
  task tests, 11 arm-Web integration tests and 15 browser input tests. The new
  tests execute Baseline, Localized Baseline direct relocation and Advanced
  line-follow relocation through shared fake sessions and the real HTTP route.
  The six
  non-Qt repository suites passed 222 tests; Console discovery passed 146 tests
  and could not import two legacy PySide6 modules because PySide6 is absent
  (148 tests discovered in total).
  `git diff --check` passed with only existing line-ending conversion warnings.
- No hardware discovery, credential read, device connection, command, service
  action or motion occurred.

## Outstanding matters

- Real-device L4 acceptance is explicitly out of scope and remains separately
  gated after the other CLI session is finished.
- The concurrent full-Baseline CLI goal completed at `cd18cdc`; focused tests
  were repeated against that new HEAD before this goal was staged.
- Commit and push are pending at plan-finalization time.

## Experience signal (for manual review)


## Intent to submit

```text
feat: manage drawing modes from web console
```
