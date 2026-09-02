# Arm YOLO Manual Engineering Control

- Status: `completed (L1); deployment pending`
- Responsible: `joint`
- Highest validation level: `L3`

## Objective

Replace the one-use arm action and application-level motion admission with an
explicit YOLO/manual engineering mode. Expose repeatable relative jog commands
for all six joints and the X/Y/Z user-coordinate axes to both the computer API
and Hardware console. Default UI increments are 2 degrees for joints and 5 mm
for Cartesian translation.

## Initial workspace state

The `main` worktree contains uncommitted work from the immediately preceding
arm L3 diagnosis and independent-arm UI correction. Those paths are owned by
this same active effort and overlap the controller/UI files required here. No
user-owned or unrelated dirty path will be modified. Raw resource archives and
local device configuration remain read-only.

## Editable scope

- `README.md`, `.gitignore`, `docs/overall-plan.md`, and focused arm,
  console, and deployment documentation
- `protocol/` arm motion contract and vectors
- `src/robot_arm/runtime/` and its project builder
- `src/maixcam/arm/` command routing and admission
- `src/console/` arm client/runtime/controller/UI
- `tools/robot_cli.py` and `tools/robot_arm/build_dobotstudio_project.py`
- focused tests under `tests/robot_arm/`, `tests/maixcam/`, and `tests/console/`
- this plan, the superseded single-joint plan, and `plan/log.md`

## Read-only scope

- `ESP32/`, `Camera/`, and `Robot Arm_Claws/`
- robot IP settings, TCP232 settings, controller firmware, payload, taught
  points, user/tool calibration, native joint limits, collision configuration,
  and emergency-stop configuration
- chassis runtime and CAN behavior

## Confirmed boundary change

The user explicitly requested YOLO/manual engineering control and rejected the
one-use application gate as disruptive to development. In this mode:

- arm motion is independent of ESP32/chassis state;
- no application lease, one-use token, repeated enable, or attended checkbox is
  required for arm jog commands;
- the computer API and UI may repeatedly request joint-relative and XYZ-relative
  moves;
- transport validation still rejects malformed, non-finite, or unsupported
  messages, while physical joint limits, collision handling, and emergency stop
  remain owned by the Dobot controller.

## Expected work

1. Replace `L3J1CYCLE` with reusable relative-joint and relative-user-linear
   primitives implemented only with E6 4.6.0.3 controller-Python whitelist APIs.
2. Add MaixCam and computer client mappings for the new commands without a
   named one-use admission file.
3. Replace the Hardware one-shot UI with compact J1-J6 `- / +` controls and
   X/Y/Z `- / +` controls, using 2-degree and 5-mm defaults.
4. Generate a DobotStudio YOLO project and validate all affected local layers.
5. Deploy and perform L2/L3 only after the user explicitly requests deployment
   and confirms the current physical test conditions.

## Validation

- L0: full diff review, `git diff --check`, secret/raw-resource audit.
- L1: focused robot-arm, MaixCam, console-client/runtime/UI tests; generated
  project inspection and Python compilation.
- L2/L3: not automatic. Record as not run until explicitly performed.

## Intent to submit

```text
feat(arm): add repeatable YOLO manual jog control
```

## Actual results

- Replaced the controller-consumed `L3J1CYCLE` grant with repeatable
  `RELJOINT` and `RELLINEAR` primitives. The former calls `RelJointMovJ`; the
  latter calls `RelMovLUser` with zero rotational delta.
- Added `arm.jog_joint` and `arm.jog_xyz` to the MaixCam envelope, computer
  client, background runtime, CLI, and Hardware UI. Absolute joint, absolute
  Cartesian, and gripper calls are also admitted by YOLO mode.
- Removed the MaixCam named one-use admission module and all arm UI unlock/L3
  one-shot controls. Arm availability depends only on its own connected route,
  idle task state, and controller-reported YOLO motion status, not ESP32 state
  or the fault panel.
- Generated the ignored DobotStudio project at `build/robot-arm-yolo`. Its
  `var.py` has `YOLO_MODE = True`; generated source compiles and contains
  `RelJointMovJ` and `RelMovLUser`, with no TCP/IP-only command-ID APIs.
- L1 passed: 172 tests plus 6 subtests across protocol, robot-arm, MaixCam,
  console, and development tooling; the offscreen UI smoke test and Python
  compilation passed. A whole-repository pytest invocation remains blocked at
  collection by the pre-existing duplicate `chassis_tcp_probe` module-name
  collision between ESP32 and console tests. Focused subsystem suites pass.
- L2/L3 were not run for this YOLO build. No device file was changed and no
  motion command was sent during this implementation.
