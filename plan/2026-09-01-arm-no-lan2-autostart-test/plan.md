# Validate robot arm without LAN2 path

- Status:`completed`
- Date:`2026-09-01`
- Highest validation level:`L3`
- Submission intent: Only this target plan and fact log will be submitted after the test is completed

## Objective

Distinguishing and verifying two questions: whether the existing TCP project has been operational since the arm's cold was activated, and whether the removal of the LAN2 after the project was initiated by the LAN2 is still capable of continuous diagnosis and control by MaixCam through UART/TCP232 and the robot arm LAN1.

## Initial state of the workspace

- Current branch:`target/maixcam-arm-l2`
- Workspace has been modified:`.vscode/settings.json`
- This change has nothing to do with this goal, does not check the content, does not modify, does not hold.

## Document ownership

Modifyable:

- `plan/2026-09-01-arm-no-lan2-autostart-test/plan.md`
- `plan/log.md`
- `tmp/legacy_arm_once.py`(neglected single test tool)
- `tmp/run_guarded_legacy_once.sh`(overlooking UART protection portal)

Read only:

- `src/maixcam/arm/`
- The legacy robot-arm communication-example directory under `Camera/code/used/`
- `protocol/arm-diagnostic-v1.md`
- `docs/robot-arm/lan1-diagnostic.md`
- MaixCam's current deployment catalogue, existing robot arm engineering and TCP 232 configuration

Scope of protection:

- Do not modify robot arm IP, TCP 232 mode/parameter, taught point, speed parameters or security configuration.
- No ESP32, MaixCam or robot arm products program; only MaixCam allowed `/tmp` Upload this goal single test tool, delete it after.
- Do not connect to LAN2, do not start DobotStudio.

## Expected work

1. Read only MaixCam SSH.`/dev/ttyS0`Owner and existing protected UART entrance.
2. User confirm L3 site secure doors, LAN2 unconnected and single fixed P2 expected movements.
3. Since the robot arm is initially at P2, send it one time.`Initialize`Go to P1 and wait for user confirmation, send one more time`biao00300031-020`returns P2; reading old programs every step`yunxing`Response.
4. It is prohibited to try again automatically; abnormally, stop when the time is exceeded or the result is unknown and confirm the actual state by the person on the scene.
5. Restore MaixCam's original UART owner, record actual movements, respond and no LAN2 path conclusion.

## Risks and conditions of cessation

- The old program will`biao`The coordinates that follow are used only for decomposition and actually fix execution`MovJ(P2, {"user": 0, "v": 100})`.
- `yunxing`Back before the action, only the request is accepted, not the action is complete.
- Before sending, you must confirm the location of the person, the physical presence, the physical presence, the perimeter clean, the chassis fixed, the robot arm secure position, the overall low speed and load.
- Direction, speed, range anomaly, repeat actions, immediate physical stoppage and stop software operations when communication is out of time or when on-site observations are inconsistent.

## Validation

- L0: `git diff --check`Plan discrepancies and secret checks.
- L2: MaixCam SSH, owner of UART, no LAN2 and TCP232 physical state confirmed on site with read-only inspection.
- L3: Only one fixed old protocol message sent; user on-site observation of P2 actions and confirmation of final state.
- Do not perform chassis actions;`Initialize`and`biao`It's carried out in two manual delegations, and it's not automatic.

## Actual results

- The user's description of "P2 has reached" is the location of the front arm of the test, not the result of the current test; Agent did not send any motion orders prior to that, and could not be judged to have passed.
- Users then renewed their authorization for immediate execution, and maintained readiness conditions for site stop, clean empty, chassis fixed, secure, low speed and load.
- For the first time that LAN2 was not connected, Agent sent the old protocol accurately through the protected UART portal`Initialize`MaixCam wrote the whole story, but it didn't come in two seconds.`yunxing`, the user confirmed that the arm of the machine was not moving at all; there was no re-emergence, nor did it continue.`biao`.
- Following confirmation that the arm of the machine actually works is the RPA1 diagnostic work in this repository.`Initialize`It's not part of the project agreement, so the timeout of the old agreement does not in itself prove that LAN2 is the necessary link for the running period.
- After the user reconnects LAN2 and starts RPA1, MaixCam sends non-motion`PING`Success, 326 milliseconds, robot arm back.`ready`.
- The user unplugs LAN2 and waits for 10 seconds before MaixCam retransmits motionless`PING`Success, rounding 194 ms; returning`ready`, `motion_enabled=false`and`fixed_step_consumed=false`.
- Following the clear L3 security clearance of this round, Agent sent RPA1 only once.`STEP`J1 is heading 1°, waiting for 1 second, reverse 1°, speed and acceleration 5%, no automatic retest. Robot arm returns successfully, 3201 ms, eventually`ready`, `motion_enabled=false`and`fixed_step_consumed=true`; user confirm movement is normal.
- Verified: once RPA1 is running, unplugging LAN2 does not interrupt the `MaixCam /dev/ttyS0 → TCP232 → robot arm LAN1` runtime path. LAN2 does not carry runtime control data.
- After testing exit`/dev/ttyS0`Restored held by launcher; MaixCam `/tmp`and local`tmp/`The old protocols have been deleted.
- ESP32 and chassis were not involved; no changes were made to robot arm IP, TCP 232 parameters, safe configuration, taught point, product program or robot arm engineering.

## Conclusions and residual risks

- Adopted: LAN2 can be removed when RPA1 is activated; MaixCam completes a two-way state communication and a controlled real action.
- Failure to pass/no validation: whether robot arm cold start and physical enabler will automatically start RPA1. Current facts continue to indicate that "substantive enabler" is not a substitute for "confirmation that the project is running".
- Every time a machine arm repowers, the RPA1 should be activated through LAN2/DobotStudio and non-motion prior to configuration and validation of a reliable startup mission or local launch entrance.`PING`Confirm.`ready`;to remove LAN2.
- Old agreement`Initialize`/`biao`The RPA1 diagnostic protocol is not the same operating contract and cannot be used; this target does not verify arbitrary coordinates control or completion of feedback on old projects.
- The stationary STEP of this round only proves that the established single low-speed motion link does not represent a universal action interface, a break-up recovery, semantics, or up-to-date self-start.
