# Get Maixcam to the machine arm LAN1 link and carry out a controlled exercise.

- Status:`completed`
- Responsible: Agent implemented, user on-site supervision and operational entities stopped
- Highest validation level:`L3`

## Objective

Establish the bidirectional diagnostic loop over the frozen `MaixCam UART → PCB TCP232 → robot arm LAN1` topology. First replace legacy raw strings with versioned `PING/PONG` framing, sequence, CRC, and timeout. Then, under an explicitly authorized L3 safety gate, execute one fixed low-speed J1 movement that returns to its starting pose. The request carries no angle, speed, or taught-point parameters, and the robot-arm project accepts it at most once.

## Initial state of the workspace

```text
## main...origin/main
 M .vscode/settings.json
```

Synchronized from `main` Create `target/maixcam-arm-l2`.`.vscode/settings.json` is that the user has changed, this target is read-only, not overridden, not stored, not submitted. MaixCam SSH and ESP32 WebREPL are online at start of the check; MaixCam RTSP is not running, not related to this target, not automatically.

## Modifyable File

- `protocol/`
- `src/maixcam/arm/`
- `src/robot_arm/diagnostics/`
- `tests/protocol/`, `tests/maixcam/`, `tests/robot_arm/`
- `tools/maixcam/`
- `.vscode/tasks.json`
- `README.md`
- `docs/overall-plan.md`
- `docs/network/README.md`
- `docs/maixcam/`, `docs/robot-arm/`
- `plan/2026-09-01-maixcam-arm-l2/plan.md`
- `plan/log.md`

## Read-only files and directories

- `.vscode/settings.json`
- `ESP32/`, `Camera/`, `Robot Arm_Claws/`
- `src/esp32/` and ESP32 device file system
- MaixCam's current video program and camera resources
- Robot arm old projects, teaching points, IP, security parameters and established motor configuration
- Local Secret, SSH Configuration, Device Backup and Real Address Overwrite

## Shared Dependencies

- (b) MaixCam is controlled by UART/TCP232, and LAN2 is used only for maintenance and deployment.
- Used camera data `/dev/ttyS0`, 115,200 pert access path to robot arm; the real-time check must confirm that the device node is not occupied by launcher or other processes.
- TCP 232 baseline is 115200 8N1, TCP Client, target arm `192.168.5.1:5200`;no changes before exporting the current configuration.
- Old example of robot arm received `Initialize` or `biao...` It's called. `MovJ`, this goal prohibits sending these strings and must stop the project.
- `protocol/runtime-status.schema.json` Structured state and error code principles.

## Risk and safety door

- The L2 stage robot arm diagnostic project will only be accepted `PING` And back `PONG`; the stage is completed and the robot arm is not moving.
- L3 increases fixed. `STEP`: J1 is heading 1°, waiting for 1 second, J1 is heading back 1°; speed and acceleration are 5%, smooth transition is off. Request not to carry motion parameters, robot arm projects are initiated at most once, MaixCam does not retry automatically.
- Prior to connection or startup, the user must confirm that the person is on the scene, that the entity is inoperable, that the robot arm is not functioning and that the old motion program has stopped. If the body is likely to generate action by automatically running the old project, stop and upgrade to L3.
- MaixCam read the target directory and serial occupancy before writing, back up the replacement project file; deployed to a stand-alone directory, without covering video or visual items.
- Do not change the robot arm IP, TCP 232 working model/parameters or security configuration; Stop and request user confirmation if present value is inconsistent with baseline.
- The diagnosis failed only to report the disconnection, occupation, CRC, serial number or timeout, not sending an old detective command, not automatically retrying the motion, not restarting the arm of the machine. An anomaly occurred in the action of an immediate operator; if the first action fails, the compensatory action is not automatically sent.
- (c) MaixCam's backup is used to restore the pre-occupy state.

## Expected work

1. Defines the ASCII diagnostic frame, CRC, serial number, maximum length, timeout and wrong semantic.
2. MaixCam can be injected into the UART gateway and the independent L2 probe, explicitly checking the chain of ownership and forcibly rejecting sports orders.
3. Make the robot arm LAN1 non-motion resonance project and static proof that it does not contain motion API or teaching points.
4. Add cross vectors, fractions/ sticky packages, CRC, timeout, error response, serial occupancy and motion rejection of test and VS Code mission.
5. L1 read-only check MaixCam `/dev/ttyS0`, processes and TCP 232/robot arm maintenance state.
6. After users started the robot arm diagnostic program through LAN2, deployment of MaixCam diagnostic catalogue and implementation of one. `PING/PONG`A broken chain timed out and restored.
7. Users clearly confirm at 2026-09-01 that the site is shut down, that the chassis is unobstructed, that the chassis is fixed, that the arm is secure and the load is confirmed, and that the above-mentioned fixed action is authorized. Extension protocol, once achieved and tested, is deployed and only issued once. `STEP`.

## Validation

- L0: VS Code JSON, Document, Configure Template, Official Source ASCII and Secret Scan.
- L1: protocol, MaixCam gateway, resource ownership, robot arm diagnostic resolutioner and safety source code test; all retrogressive.
- L2: MaixCam UART Two-way `PING/PONG`The machine has passed, about 163 ms, and the full robot arm is motionless.
- L3: Only one fixed J1 move is performed under the user's on-site supervision; confirm that it is heading to 1°, stopping for one second, turning back to 1°, then suspending the project and failing to function. Any abnormal physical emergency stoppages; no automatic retry is allowed without a complete response.
- `git diff --check`
- `git status --short --branch`

## Actual results

- Create `RPA1` ASCII frame, CRC-16/CCIT-FALSE, Serial number, 96 byte cap, fraction/ sticky package restoration, timeout and stabilization error codes; L2 accepted only `PING/PONG`.
- MaixCam has formed a POSIX UART transmission, an on-line request gateway, L2/L3 independent probe and launcher guard script. Protect scripts to identify subvisor and UART owners, temporarily release `/dev/ttyS0`, restore launcher.
- DobotStudio Pro 4.6 robot arm forms independent `main.py`.L3 extension accepted only without parameters `STEP`, hard-coding J1 is heading 1°, waiting for 1 second, reverse 1°, speed and acceleration 5%,`cp=0`; maximum consumption per project running, failure or response loss without retrying.
- L2 is real. `PING/PONG` Success, Serial 1, 163 milliseconds, robot arm motionless.
- Users complete L3 security confirmation and perform two separate manual validations. First return `DONE`, 3525 milliseconds to and from, but not observed by, the system refuses to reissue directly. The user stops and reruns the robot arm project, returns again after reauthorization `DONE`3221 milliseconds, user confirmed link.
- After the L3 exit, launcher supervisor remains active; eventually `/dev/ttyS0` The owner is `/maixapp/apps/launcher/launcher`...does not modify robot arm IP, TCP 232 parameters, security parameters, taught points, chassis or video services.
- L0/L1 Final validation: protocol 10, ESSP32 30, MaixCam 40, robot arm 7, development tool 23, 110; 31 Python file checking, 52 VS Code missions, JSON, Bash syntax, validation of workspace `git diff --check` Pass.

## Outstanding matters

- (b) The local gateway timeout and error path test has been passed. If the real machine is subsequently broken, a separate target must be set and action results marked as unknown, and automatic retry is prohibited.
- This target only validates a fixed action, not a generic robot arm operating protocol. Any trajectory, status queries, queues, cancellations, recovery and control table integration needs to have another target.
- MaixCam video is not operational at the start of this target, not related to robot arm links; this target is not active or modified for video services.

## Intent to submit

```text
feat: validate maixcam arm lan1 link
```
