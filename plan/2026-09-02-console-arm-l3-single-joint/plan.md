# Console Arm L3 Single-Joint Motion

- Status: `in-progress`
- Responsible: `joint`
- Highest validation level: `L3`

## Objective

Implement and validate one deliberate, low-speed, bounded single-joint action
from the Hardware console through the deployed MaixCam and LAN1 arm route.
The first action must be opt-in, visible in the journal, terminally reported,
and leave all Cartesian, gripper, and arbitrary multi-joint controls disabled.

## Initial workspace state

```text
## main...origin/main
```

There are no uncommitted paths. The preceding L2 goal was committed and pushed
as `28444c0`.

## Editable scope

- `src/console/ui/` and focused console tests
- `src/maixcam/arm/` and focused MaixCam tests
- `src/robot_arm/runtime/` and focused controller-service tests
- `docs/robot-arm/` only if the deployed L3 procedure changes
- `plan/2026-09-02-console-arm-l3-single-joint/plan.md`
- `plan/log.md`

## Read-only scope

- Raw-resource archives: `ESP32/`, `Camera/`, `Robot Arm_Claws/`
- ESP32, CAN, TCP232 configuration, arm network configuration, LAN2 settings,
  taught points, payload/tool/user-frame settings, and credentials
- Existing local configuration and all device content until a source-review and
  target-path confirmation precede deployment

## Shared dependencies

- RPA2 framing and the deployed default-deny controller service.
- Computer -> MaixCam TCP 8780 -> UART0 -> TCP232 -> arm LAN1 route.
- The console's Hardware/manual-session semantics and status mapping.

## Risk and safety gate

- Risk: real single-device motion and a controller-source deployment change.
- Hardware: MaixCam, TCP232, and robot arm; ESP32/chassis must remain unused.
- User operations: the user confirmed an on-site operator, available physical
  emergency stop, clear space, safe pose, low speed, and unloaded arm for this
  single-joint test.
- Recovery: the physical emergency stop and controller stop remain primary;
  the currently deployed default-deny project can be re-imported/restarted via
  LAN2 if the controlled version fails. No controller network or safety setting
  will be changed.
- Motion gate: only after local tests, source review, route status `ready`, and
  deployment confirmation. The first hardware request will be a named,
  bounded, single-joint delta at no more than 10% speed/acceleration. Stop on
  unexpected pose, controller error, missing lifecycle response, or user stop.

## Expected work

1. Inspect the existing RPA2 controller and MaixCam implementations, then add
   a named low-speed single-joint action with immutable bounds and terminal
   lifecycle reporting.
2. Bind that action in the Hardware console behind an attended L3 explicit
   enable; preserve default-deny after the action and keep arbitrary forms
   hidden.
3. Test locally, deploy only reviewed source to the confirmed existing service,
   perform L2 readiness, then issue one approved L3 action under supervision.

## Validation

- `git diff --check` and `git status --short --branch`.
- Focused service/gateway/console tests and syntax compilation.
- L2: `PING`/`STATUS`, ready state, default deny before the action.
- L3: with the user's confirmed site gate, request the named single-joint test
  once, observe `ACK`/`RUNNING`/`DONE` or a terminal fault, observe the arm,
  then recheck `STATUS` showing idle/ready. Never retry automatically.

## Actual results

- L1 implementation: added parameterless `L3J1CYCLE`, which consumes a
  controller-local one-use policy before sending a relative J1 `+1°`, one
  second wait, and `-1°` cycle at 5% speed/acceleration. It never enables the
  generic `MOVEJ`, `MOVEL`, or `GRIPPER` paths.
- The MaixCam admission layer accepts only the named test action when its
  temporary ignored admission file names that action. Its tracked default
  remains deny-all. The Hardware console hides generic forms, requires its own
  attended checkbox plus Online arm route and ESP32 `safe idle`, and records
  returned MaixCam lifecycle evidence without claiming measured terminal pose.
- L1 passed: 13 robot-arm tests, 51 MaixCam tests, and 49 console tests;
  generated DobotStudio test project inspection, Python compilation, and
  `git diff --check` also passed. No device file, network setting, or motion
  command has been written or sent.

## Outstanding matters

- The user must connect LAN2 and import/start the generated temporary
  DobotStudio project at `tmp/robot-arm-rpa2-l3-j1-cycle/`; the current
  default-deny project remains the recovery option.
- Before action, deploy the compatible MaixCam endpoint source and its
  temporary named admission file, then obtain L2 route readiness and ESP32
  `safe idle` in the Hardware console. These pending operations are L2 only.
- L3 execution and post-action default-deny restoration have not run.

## Intent to submit

```text
feat(console): add bounded arm L3 test action
```
