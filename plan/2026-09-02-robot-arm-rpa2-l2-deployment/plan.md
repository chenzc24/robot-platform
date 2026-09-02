# Robot Arm RPA2 L2 Deployment

- Status: `completed`
- Responsible: `joint`
- Highest validation level: `L2`

## Objective

Deploy the committed, default-deny RPA2 LAN1 controller project to the Magician E6 through LAN2/DobotStudio Pro; start it as a resident TCP service; then verify only `PING`, `STATUS`, and motion-command rejection through the MaixCam/TCP232 route after LAN2 is disconnected.

## Initial state of the workspace

```text
## main...origin/main
```

The active main worktree is clean. The separate primary worktree contains a user-owned `.vscode/settings.json` change and remains untouched.

## Modifyable files

- `plan/2026-09-02-robot-arm-rpa2-l2-deployment/plan.md`
- `plan/log.md`
- `tools/robot_arm/` and directly related L1 tests for a DobotStudio project builder
- `src/maixcam/arm/arm_service_config_example.py`, its direct imports, and related L1 tests: correct the required default-deny configuration-module name before deploying the RPA2 gateway
- `src/robot_arm/runtime/README.md`, deployment documentation, and integration documentation where the deployable project shape is described
- ignored local controller-project export, screenshots, and release evidence under `device-backups/robot-arm/`

## Read-only files and directories

- `ESP32/`, `Camera/`, and `Robot Arm_Claws/`
- all ESP32 source/device files
- MaixCam device files except the isolated `/root/robot-platform/arm/` RPA2 gateway release directory; no video process, camera owner, TCP232 configuration, or other device path may be modified
- `src/robot_arm/runtime/main.py`, `src/robot_arm/runtime/arm_motion_service.py`, `src/robot_arm/runtime/var.py`, and `protocol/motion_link.py`; they remain the reviewed modular release input and will not be edited
- TCP232 addressing/mode/UART configuration, arm IP settings, taught points, payload, frames, load, gripper settings, and controller safety settings
- credentials and user-owned local configuration

## Shared dependencies

- `src/robot_arm/runtime/` plus `protocol/motion_link.py` are the reviewed modular source; a local builder produces the two-file DobotStudio project.
- RPA2 protocol uses `protocol/motion_link.py` and LAN1 `192.168.5.1:5200`.
- MaixCam arm gateway is now the required L2 test transport. It will be deployed only to `/root/robot-platform/arm/`, with its default-deny configuration, after the controller project has been started. Its ownership guard must restore the MaixCam launcher supervisor when it exits.
- `var.py` keeps `MOTION_ENABLED = False` and all motion bounds unset.

## Risk and safety gate

- Risk: controller project overwrite and LAN1 service ownership. This goal is L2 only and must not call arm motion APIs.
- Hardware: robot arm controller, LAN2 maintenance cable, LAN1/TCP232, MaixCam only for a later non-motion probe.
- User operations: connect computer to LAN2, set or confirm the computer maintenance address, use DobotStudio Pro to retain the existing project and import the reviewed bundle as a separate project, then start it. The user retains control of controller enable/Run/Stop and the physical emergency stop.
- Backup and recovery: the user declined an export backup. The existing controller project must therefore remain intact and identifiable; recovery is reopening that untouched project through LAN2. Do not select a workflow that overwrites or deletes the existing project, and do not change network, taught-point, payload, or safety configuration.
- Motion gate: no motion is authorized. Do not change `MOTION_ENABLED`, blank bounds, speed/acceleration policy, or send `MOVEJ`, `MOVEL`, or `GRIPPER`. Any such test is a separate L3 goal requiring a fresh explicit on-site safety confirmation.

## Expected work

1. Run local runtime and protocol tests; build and static-check the self-contained `main.py` plus `var.py` DobotStudio project and record its Git version.
2. Confirm LAN2 reachability and controller idle state; retain the existing project and import the two-file bundle as a distinct DobotStudio Pro project.
3. Correct the MaixCam gateway's configuration-template module name, run its L1 test, and deploy only the RPA2 gateway release directory with motion admission disabled.
4. Start the project, confirm it is blocked at `TCPRead`, and verify LAN1/TCP232 settings without modifying them.
5. Disconnect LAN2 and perform only RPA2 `PING`, `STATUS`, and a rejected motion-command check through the MaixCam/TCP232 path.
5. Record facts, residual risks, and the rollback project; commit and push only deployment records if source does not change.

## Validation

- L1: isolated robot-arm runtime/protocol tests and static verification of the two-file project bundle.
- L2: LAN2 controller import/start; `TCPRead` waiting state; TCP232 configuration readback; MaixCam-to-LAN1 RPA2 `PING`, `STATUS`, and motion rejection after LAN2 disconnect.
- `git diff --check`
- `git status --short --branch`

Acceptance requires controller-level evidence, not merely a successful import or open socket. Any unknown controller state, unexpected motion, modified network setting, or inability to identify a rollback project stops the goal.

## Actual results

- An initial six-file bundle was prepared but not deployed. The operator then confirmed that the current DobotStudio project workflow accepts only `main.py` and `var.py`; the bundle is therefore invalid for deployment and will be replaced by a generated self-contained two-file project.
- Added `tools/robot_arm/build_dobotstudio_project.py`. It preserves the repository's reviewed modular source but inlines the RPA2 protocol and arm service into an import-free controller `main.py`. The deployable code remains `main.py` plus `var.py`; `prj.json` and an empty `point.json` are required import metadata.
- L1 passed: 11 robot-arm tests and 28 protocol tests. The generated bundle contains self-contained `main.py` (18,516 bytes), `var.py` (576 bytes), `prj.json`, and empty `point.json`; it compiles as Python, retains `MOTION_ENABLED = False`, and has no `arm_motion_service` or `motion_link` imports. The default policy responds to status and rejects motion without invoking a controller API.
- Corrected a MaixCam deployment blocker: `arm_command_server.py` imports `arm_service_config_example`, so the template is now stored under that importable Python-module name. A focused configuration test plus the full 47-test MaixCam suite passed.
- The user imported and started the default-deny controller project. MaixCam SSH confirmed its launcher supervisor (`296`) and launcher UART owner (`616`) before gateway start. The RPA2 release was uploaded only to `/root/robot-platform/arm/`, then its ownership guard released UART0 and started `arm_command_server.py` (`889`) on `0.0.0.0:8780`; `fuser /dev/ttyS0` confirmed the gateway alone owned UART0.
- L2 runtime interaction passed over the actual computer Wi-Fi -> MaixCam -> UART0 -> TCP232 -> arm LAN1 route: `arm.ping` sequence 1 returned `RECEIVED`, `ACCEPTED`, and `DONE` with downstream `protocol=2`; `arm.status` sequence 2 returned `DONE` with `service_state=ready`, `motion_enabled=0`, `active_sequence=0`, and `last_error=none`. A test `arm.move_joint` sequence 3 was rejected by MaixCam as `admission_rejected` before any UART/controller motion command; no motion was requested from the arm service.
- The computer's LAN2 adapter now has `192.168.200.10/24`, so the maintenance cable remains physically connected. The route has not yet been repeated after physically disconnecting LAN2; that is the remaining L2 independence check.
- After LAN2 was disconnected, a repeated `PING` exposed a recoverability defect: `arm_command_server.py` created a fresh RPA2 gateway for every computer connection, resetting the downstream sequence to 1 while the controller correctly retained its last sequence. The first reconnect `PING` was rejected as `sequence_replay`; no motion command reached UART or the controller. The gateway must retain its downstream sequence across computer sessions before the independence check can pass.
- The first repair retained the gateway across computer sessions, but the mandatory gateway restart itself again began at sequence 1 while the arm service retained its prior sequence. The first post-restart `PING` was correctly rejected as `sequence_replay`; later downstream sequences 3 and 4 succeeded. The gateway must seed a restarted process above the controller's typical persisted sequence before the final LAN2-disconnected proof.
- Final L2 acceptance passed with LAN2 physically disconnected (Windows Ethernet adapter `Disconnected`). The deployed gateway was restarted under its ownership guard, then two separate computer connections completed `PING` and `STATUS` through MaixCam/TCP232/LAN1. Their downstream sequences were `1788328439` through `1788328442`, demonstrating both restart and reconnect continuity. Both test `arm.move_joint` requests were rejected as `admission_rejected` at MaixCam before UART transmission. No arm motion, controller motion API call, TCP232 setting change, or arm network setting change occurred.
- At handoff the user-requested resident gateway remains running as MaixCam PID `1182`, owns `/dev/ttyS0`, and listens on TCP `8780`. The historical controller `last_error=sequence_replay` remains visible after the earlier rejected replay, while `service_state=ready` and `active_sequence=0` confirm no active fault or task.

## Outstanding matters

- A future L3 goal must populate reviewed arm policy bounds and separately receive an immediate physical motion-safety authorization before any motion admission is enabled.
- Gateway restart uses a bounded wall-clock sequence seed to exceed the controller's existing low test sequence. If controller time is invalid or the arm service has already accepted a larger sequence, restart the arm service through its controller workflow and repeat L2 `PING` before relying on the gateway.

## Experience signal (for manual review)


## Intent to submit

```text
deploy(robot-arm): record default-deny RPA2 LAN1 service
```
