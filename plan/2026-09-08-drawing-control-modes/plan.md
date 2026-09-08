# Baseline and advanced PC drawing relocation modes

- Status: `completed`
- Responsible: `agent`
- Highest validation level: `L1`

## Objective

Provide two explicit computer-side relocation strategies for the drawing task:

- `baseline`: no line following and no AprilTag dependency; command a bounded
  straight chassis displacement using velocity refresh plus STOP, then update
  the drawing offset from the commanded distance.
- `advanced`: ask the ESP32 to run its local line-following loop to a confirmed
  station, then require a fresh PC AprilTag localization generation and use its
  measured drawing offset.

The computer owns strategy selection and task orchestration. ESP32 retains
motor, sensor-loop, watchdog and low-level stop ownership. This specializes the
existing architecture; it does not transfer the sensor loop to the computer.

## Initial workspace state

- Worktree: `E:\Device Network-drawing-control-modes`
- Branch: `target/drawing-control-modes`
- Base: synchronized `origin/main` at `a5c24b0`
- Primary worktree is 13 commits behind and has unrelated user/other-goal
  changes. It remains read-only and unstaged.

## Modifiable scope

- `.gitignore` (one explicit local mode-config exclusion)
- `README.md` (one documentation link)
- `docs/overall-plan.md`
- `protocol/chassis_tcp_v3.py`, `protocol/chassis-tcp-v3.md`, and v3 vectors
- `src/esp32/app/chassis_motion_tcp_service.py`
- `src/esp32/app/chassis_runtime_factory.py`
- `src/esp32/app/device_config.example.py`
- `src/esp32/app/line_follow_runtime.py`
- `src/esp32/README.md`, `docs/esp32/line-following.md`
- `src/console/chassis_motion_tcp_client.py`
- `src/console/motion_router.py`, `src/console/runtime_core.py`
- `src/console/drawing/control_modes.py` and package exports
- `config/drawing-control.example.json`
- directly related protocol, ESP32 and console tests
- `docs/console/drawing-control-modes.md`
- this plan and append-only `plan/log.md`

## Read-only scope

- Existing drawing geometry/planner and AprilTag/localization implementation
- MaixCam, robot-arm runtime, UI, raw-resource archives and device files
- Primary worktree local settings, demo changes, logs and diagnostic plans

## Shared contracts and decisions

- Existing RCP/TCP v3 direct velocity and watchdog behavior remains unchanged.
- Add optional line-follow start/stop/status messages. A runtime without a
  configured follower rejects them; direct velocity remains available.
- Baseline distance is an open-loop commanded estimate, never measured travel.
- Advanced station detection is local to ESP32; AprilTag metric relock stays on
  the computer and must publish a new generation after the chassis stops.
- No automatic fallback from failed advanced mode to baseline: mode selection is
  explicit before motion, so a sensor or localization failure stops instead of
  silently changing behavior.

## Expected work

1. Extend the optional chassis line-follow control/status contract and PC client.
2. Integrate the existing injected `LineFollower` into the ESP32 scheduler only
   when ignored local pin/tuning configuration explicitly enables it.
3. Implement strict PC relocation configuration plus baseline and advanced
   strategies using injected clients, clocks and localization state.
4. Emit structured results carrying mode, offset source, commanded/measured
   distance, generation and confidence rather than conflating the two modes.
5. Add deterministic L1 protocol/service/client/strategy tests and update docs.

## Safety and validation

- No device connection, deployment, GPIO/CAN access, service start or motion.
- Committed defaults keep line following disabled and production readiness
  false. Baseline calls require explicit arm-safe, attended and emergency-stop
  admission data, bounded distance/speed, and always attempt STOP.
- L1 validation: targeted and affected regression suites, source checks, JSON
  parsing, protocol vectors, diff/secret/staged-scope audits and branch sync.
- L3/L4 deployment and movement require a new safety confirmation and physical
  validation of time-distance scale, pins, polarity, steering, station geometry,
  stop distance, AprilTag layout and coordinated arm-safe gates.

## Actual results

- Added explicit PC-selected `baseline` and `advanced` relocation strategies.
  Baseline uses bounded refreshed direct velocity plus an unconditional STOP and
  labels its offset evidence `commanded_open_loop`. Advanced starts and polls
  the ESP32-local follower, stops at a confirmed station, and accepts only a
  newer locked AprilTag localization generation.
- Added optional RCP/TCP v3 line-follow start/status/stop messages, PC client and
  router exposure, and an ESP32 runtime adapter that creates GPIO inputs only
  when ignored local configuration explicitly enables the feature. Committed
  defaults leave both production readiness and line following false.
- The drawing planner boundary is exposed by `relocate_reposition_plan`, which
  consumes one `reposition.required` barrier and returns its exact checkpoint,
  updated JSON-axis offset, and mode-specific evidence. Full arm-step execution
  and UI selection remain outside this goal.
- L1 passed 60 focused tests and 340 applicable affected/full regression tests:
  protocol 28, ESP32 76, app 22, console 111, developer tools 28, MaixCam 57,
  and robot arm 18. The console run deliberately excluded two existing PySide6
  GUI modules because PySide6 is absent from the available virtual environment.
- The source checker passed all 19 changed Python paths, both changed JSON files
  parsed, and `git diff --check` passed. The workspace validator remains red for
  pre-existing non-ASCII lines in `src/console/ui/views.py`; test-created ignored
  bytecode cache directories were also reported and are not staged.
- No hardware, network service, deployment, GPIO/CAN access, device write or
  movement occurred. L3/L4 pin, polarity, steering, measured-distance and
  coordinated arm-safe validation remains required before setting either local
  production gate true.

## Intent to submit

```text
feat(console): add baseline and advanced drawing relocation modes
```

Implementation commit `9fb9291` was pushed to
`target/drawing-control-modes`; PR #10 targets `main`. No merge or deployment
was performed.
