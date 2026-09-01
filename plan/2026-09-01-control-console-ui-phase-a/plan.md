# Control Console UI Phase A

- Status: `completed`
- Responsible: `agent`
- Highest validation level: `L1`

## Objective

Deliver a runnable PySide6 desktop control-console shell that implements the approved layout in simulator mode: camera placeholder and overlay model, independent chassis and robot-arm panels, command journal, persistent fault center, deterministic fault scenarios, and safe default hardware mode. No real device connection or motion is part of this goal.

## Initial state of the workspace

The goal begins from a clean and synchronized UI-design branch:

```text
## target/control-console-ui-design...origin/target/control-console-ui-design
```

Implementation runs in the isolated worktree `E:\Device Network - control-console-ui-phase-a` on `target/control-console-ui-phase-a`. The primary worktree, all existing device worktrees, user-owned `.vscode/settings.json`, device filesystems, and raw-resource archives remain outside this goal.

## Modifiable files

- `requirements-dev.txt`
- `src/console/README.md`
- `src/console/ui/`
- `tests/console/test_control_console.py`
- `docs/console/control-console-ui.md`
- `plan/2026-09-01-control-console-ui-phase-a/plan.md`
- `plan/log.md`

## Read-only files and directories

- `protocol/`
- existing `src/console/chassis*_client.py`, `src/console/maixcam_arm_client.py`, and `src/console/motion_router.py`
- `src/esp32/`
- `src/maixcam/`
- `src/robot_arm/`
- `config/`
- `tools/`
- `ESP32/`, `Camera/`, and `Robot Arm_Claws/`
- all device filesystems, local configuration, credentials, network endpoints, and hardware

## Shared dependencies

- The approved [Unified Control Console UI](../../docs/console/control-console-ui.md) design.
- Direct computer-to-ESP32 and computer-to-MaixCam runtime boundaries.
- Existing synchronous chassis and arm clients; they are deliberately not invoked in this phase.
- Command lifecycle and safety semantics in `docs/runtime/README.md`.
- `PySide6 6.11.1` is already installed in the current host Python and is added to the development dependency declaration.

## Risk and safety gate

- Risk: a desktop UI could be mistaken for a deployed hardware controller or imply that motion and stop behavior have been validated.
- Hardware: none.
- User operations: launch only a local simulator window; no network or device action is required.
- Backup and recovery: Git version controls source; no device state exists to restore.
- Motion gate: not applicable. Hardware mode has no transport adapter, every motion action is locked, the simulator labels every synthetic event, and the chassis software-stop control only records a simulator-safe request.

## Expected work

1. Add immutable state models, a deterministic simulator controller, command journal, and fault model.
2. Build a responsive PySide6 main window matching the approved layout and visual hierarchy.
3. Implement simulated connection/session controls, chassis press-and-hold controls, arm tabs and safe gating, video overlay/rotation/freeze controls, and diagnostic/fault interactions.
4. Add unit and offscreen GUI smoke tests that establish default lock state, state transitions, fault handling, and independent UI responsiveness.
5. Document the launch command, phase boundary, and unimplemented transport/video integrations.

## Validation

- `python -m unittest discover -s tests/<suite> -p "test_*.py"` for `console`, `dev`, `esp32`, `maixcam`, `protocol`, and `robot_arm`
- `QT_QPA_PLATFORM=offscreen python -m ui --smoke-test`
- `python tools/dev/validate_workspace.py`
- `git diff --check`
- `git status --short --branch`
- inspect the full diff for secrets, hard-coded device addresses, direct hardware calls, unsafe unlock defaults, and claims beyond L1.

L1 covers local simulator behavior, deterministic state changes, and an offscreen GUI construction check. No device connection, video relay, deployment, or physical motion is permitted.

## Actual results

- Added the `ui` package with immutable state models, a QObject simulator controller, video placeholder renderer, responsive PySide6 main window, command journal, active-fault surface, and module entry point.
- Added deterministic simulator scenarios for normal operation, stale video, ESP32 disconnect, arm rejection, and unknown arm outcome. Hardware mode resets sessions and rejects every transport or motion request because no real adapter exists.
- Implemented chassis connection, lease, enable, manual-unlock, press-and-hold velocity, and software-stop simulation; arm route, motion-unlock, joint, Cartesian, gripper, and lifecycle simulation; video connection, freeze, rotation, and overlay toggles. Snapshot intentionally reports `decoder_not_implemented` rather than creating a false artifact.
- Added seven focused L1 tests. The six existing test suites pass with 179 tests total: console 23, development 23, ESP32 52, MaixCam 44, protocol 28, and robot arm 9.
- The offscreen smoke test passed. Native local preview was visually inspected at 1440 x 900 and 1280 x 720; the shorter layout changes the right-side chassis/arm stack into tabs so both remain reachable.
- Workspace validation passed with no errors, source code is ASCII-only, and no device, socket, relay, credential, process, or hardware state was accessed or changed.

## Outstanding matters

- Phase B must wrap the existing clients in worker threads before any real endpoint binding.
- PyAV decoding, snapshots, local configuration, persistent session management, and any real transport remain out of scope.

## Experience signal (for manual review)


## Intent to submit

```text
feat: add simulator control console shell
```
