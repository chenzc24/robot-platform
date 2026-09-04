# Add reusable localization-lock state machine

- Status: complete; submission pending
- Responsible: agent implementation and offline validation
- Highest validation level: L1

## Objective

Add a PC-side, observation-driven localization state machine that invalidates
an old transform before possible chassis motion, waits for a confirmed logical
stop and settling interval, fuses a bounded window of accepted AprilTag poses,
locks one versioned base-from-board transform, and exposes an immutable task
context plus explicit task lifecycle methods for later coordinated drawing.
The goal must not issue a chassis or arm command of its own.

## Initial state of the workspace

```text
## main...origin/main
 M .vscode/settings.json
 M app/demo.py
 M plan/log.md
?? plan/2026-09-03-arm-xyz-singularity-diagnosis/
?? plan/2026-09-03-arm-yz-drawing-review/
?? plan/2026-09-03-video-stream-diagnosis/
```

The tracked runtime, vision, configuration and tests in this goal are clean.
The listed changes predate this goal and remain protected. Only a new appended
log hunk may later be staged from `plan/log.md`.

## Modifiable files

- `src/console/localization/`
- `src/console/runtime_config.py`
- `src/console/web_console/runtime.py`
- `src/console/web_console/server.py`
- `config/console.example.json`
- new secret-free geometry example under `config/`
- `.gitignore` for the measured local geometry override
- focused console tests under `tests/console/`
- relevant console/AprilTag documentation and repository entry links
- this plan and a new appended `plan/log.md` section

## Read-only files and directories

- `.vscode/settings.json`, `app/demo.py`, the prior unstaged `plan/log.md` hunk
- the three pre-existing untracked diagnostic goal directories
- device source under `src/esp32/`, `src/maixcam/`, `src/robot_arm/`
- all device files, ignored raw archives and ignored real local configuration
- current chassis and arm wire protocols and existing YOLO/manual semantics

## Shared dependencies

- The PC remains the high-level orchestrator; ESP32 and MaixCam responsibility
  boundaries are unchanged.
- Vision supplies accepted `T_camera_from_board` results with readiness and
  quality gates. The state machine must never promote precalibration results.
- Chassis `moving` / `enabled_stopped` is logical controller state, not measured
  wheel or IMU velocity. V1 may add a settling timer but must describe this
  limitation accurately.
- Robot feedback is `GetPose(0,0)` and remains separate from localization. A
  future task executor may combine the locked transform, returned Tool0 pose
  and configured Tool0-to-pen transform.
- Existing `/api/arm/command` remains independent YOLO/manual engineering
  control. This goal must not add a chassis gate to that route.

## Risk and safety gate

- Risk: PC runtime state/invalidation and local configuration. Incorrect state
  could later permit stale-coordinate task planning, so fail closed and test
  races/state transitions deterministically.
- Hardware: none.
- User operations: none.
- Backup and recovery: Git rollback of scoped files; no local real calibration
  is changed or committed.
- Motion gate: not applicable. L2/L3/L4 and all device connections are excluded.

## Expected work

1. Add a strict, versioned geometry loader for `T_base_from_camera` and
   `T_tool0_from_pen`, including rigid-transform validation and unready defaults.
2. Add pure SE(3) composition/inversion and bounded multi-frame pose fusion.
3. Implement a thread-safe state machine with disabled/blocked/invalid/moving/
   settling/collecting/locked states, generation tracking, explicit invalidation,
   and task begin/finish/context methods.
4. Add backward-compatible console configuration and integrate chassis status,
   motion intent, disconnect, vision updates and snapshot publication. Add only
   a safe relocalize endpoint; leave task execution as a Python API until a real
   executor owns command lifecycle.
5. Document frame conventions, logical-stop limitations and the future task
   integration surface. Add deterministic tests for configuration, transforms,
   fusion, invalidation, task generation and runtime/API integration.

## Validation

- focused localization and web-console unit tests
- complete console test suite
- full repository Python and JavaScript suites if focused checks pass
- Python compilation and JavaScript syntax
- configuration JSON parsing
- `git diff --check`
- `git status --short --branch`

L1 covers state transitions, transform math, fail-closed configuration,
concurrency-facing public methods and regression behavior. It cannot validate
physical extrinsics, stop accuracy, arm kinematics or drawing metrology.

## Actual results

- Added strict schema-1 robot geometry, rigid SE(3) validation, composition,
  inverse and stable multi-sample pose averaging. The tracked identity geometry
  remains explicitly unready and its measured local override is ignored.
- Added a thread-safe fail-closed localization machine with versioned transform
  locks, bounded unique-frame windows, chassis-motion invalidation, logical-stop
  settling, permanent configuration blocking and active/last task lifecycle.
- Console schema 5 adds disabled localization settings while schemas 3 and 4
  remain loadable. Localization additionally requires enabled complete vision.
- Integrated vision observations, chassis status/disconnect/motion intent,
  sanitized transition events, `GET /api/state`, a relocalize route and Python
  task context/begin/finish methods. Existing manual arm behavior is unchanged.
- L1 passed 324 Python tests across all seven repository suites and 14 browser
  JavaScript tests. Focused console coverage was 122 tests. Python compilation,
  JavaScript syntax, both JSON templates and working-tree diff checks passed.
- No device connection, service start, deployment, chassis command, arm command
  or physical motion occurred.

## Outstanding matters

- Physical camera/base and Tool0/pen calibration values remain future measured
  inputs. Dobot orientation convention and terminal-position verification remain
  prerequisites for a motion-producing task executor.

## Experience signal (for manual review)

- Review caught that a permanent configuration block could initially be
  overwritten by a motion event. The final state machine preserves `blocked`
  through all runtime events and has regression coverage for that case.


## Intent to submit

```text
feat(console): add localization lock state machine
```
