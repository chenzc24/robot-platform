# Freezing the MaixCam single gateway on double plane with deployment maintenance

- Status:`completed`
- Date:`2026-09-01`
- Branch:`target/single-gateway-runtime-deployment`
- Highest validation level:`L0`

## Objective

Formally write user-identified structures into the project baseline: Only computers and MaixCam must be integrated into the local area network at the time of operation, MaixCam as the only computer device gateway and connects ESP32 and TCP232/mechanic arm, respectively, through UART on both tracks;

## Initial state of the workspace

```text
## target/maixcam-arm-l2...origin/target/maixcam-arm-l2
 M .vscode/settings.json
```

Current de facto branch ratio `main` (b) This objective was established from this branch, and the facts were preserved.`.vscode/settings.json` is the user with MicroPython button configuration, unrelated to this target, keeping read-only, not saving, not submitting.

## Modifyable File

- `AGENTS.md`
- `README.md`
- `docs/overall-plan.md`
- `docs/network/README.md`
- `docs/runtime/README.md`
- `docs/deployment/README.md`
- `plan/2026-09-01-single-gateway-runtime-deployment/plan.md`
- `plan/log.md`

## Read-only files and directories

- `.vscode/settings.json`
- `protocol/`, `src/`, `tests/`, `tools/` and current VS Code missions
- `ESP32/`, `Camera/`, `Robot Arm_Claws/`
- Device File System, Local Secret, Backup, Cache and Temporary Check Directory

## Shared Dependencies

- MaixCam RTSP/H264 to computer video link and computer side FFmpeg/MediaMTX relay has passed.
- The ESP32 historical PS2/CAN chassis link has passed, but MaixCam UART to ESP32 has only old receiver skeletons and has yet to form an official motion agreement.
- MaixCam `/dev/ttyS0` Two-way diagnosis and fixation of RPA1 through TCP 232 to LAN1.
- The removal of LAN2 after the operation of the RPA1 project still completes the PING and the fixed actions; The cold startup autostart project has not yet been validated.
- `protocol/runtime-status.schema.json` It's the current service health contract, not the future mission performance.

## Expected work

1. Change the general pamphlet to a computer that only gives MaixCam a running order, which is distributed to ESP32 and robot arm, respectively.
2. New runtime baseline, definition of video, computer command, chassis UART, robot arm UART/TCP232 four channels, and unified message shell, device command set, AAK/RUNING/DonE/FAULT feedback and local security boundaries.
3. New deployment maintenance baseline, recording ESP32 WebREPL/USB, MaixCam SSH/SCP, robot arm LAN2/DobotStudio and TCP232 one-time configuration;
4. Update the network document, distinguish between the development network and the official functioning network, making it clear that the ESP32 Wi-Fi is only responsible for the development maintenance without carrying the official running order.
5. Synchronize the repository's Agent duty baseline to prevent subsequent targets from reverting to the old computer-controlled ESP32 route.
6. Give a sequence of follow-up: shared protocols and simulators, ESP32 serial services, MaixCam gateway, robot arm general services, computer adapters, and finally real machine L2/L3/L4.

## Risks and boundaries

- This goal changes only the structure decision in the document, does not achieve or deploy running codes, does not connect, writes, duplicates or drives.
- MaixCam became a single point gateway at running time, but not the only stop or bottom security controller.
- The unified message only harmonizes the semantics of the shell and the state; MaixCam must analyze and convert the device-specific command, and the transparent transmission of arbitrary motion parameters is prohibited.
- The results of the current actions following the break-up of the robot arm may still be unknown;
- The mechanic arm is still subject to manual security confirmation, enabling energy and local start-up of the configured project, unless the automatic start-up method supported is subsequently verified separately.

## Validation

- L0: Check the two-level leaps, the role, the link, the failure and the implementation phase are consistent in all entry documents.
- Check that all new link targets exist.
- Scan hot spots, SSH/WebREPL password, temporary DHCP address and private key materials.
- `git diff --check`
- `git status --short --branch`

## Actual results

- Add `docs/runtime/README.md`Freezing computers to communicate with MaixCam only expands, four channels, unified message shell, device-specific command set, command life cycle, three-end resident service, start sequence and chain break.
- Add `docs/deployment/README.md`, define ESP32 WebREPL/USB, MaixCam SSH/SCP, robot arm LAN2/DobotStudio and TCP232 configuration portals, clearly publish the order, health check and rollback principles.
- Sync `README.md`, overall, network programme and `AGENTS.md`, remove the computer from the old baseline of ESP32 by formally controlling the wi-Fi, and use the ESP32 Wi-Fi portal as a maintenance channel.
- This round changes only the document managed by the version, without connections, writing, duplicates or drives the real device; user already has `.vscode/settings.json` Modify to keep read-only and not enter submission.
- L0 check passed: All new local links exist, architecture keyword cross-scans do not reveal the old direct route, secret mode scans do not find proof; IP in the document is only the recorded robot arm LAN1/LAN2, TCP232 recommended values and clearly marked examples of hotspot segments.

## Outstanding matters

- Computer-MaixCam application connection-specific transmission, code and port are not frozen, and should be determined by simulator and test vector in the next shared protocol target.
- ESP32 Official UART chassis service, MaixCam unified gateway, Mechanic Arm common task service and computer client have not yet been achieved or deployed.
- The result of the action being carried out when the arm is broken may still be `UNKNOWN`No automatic re-testing of non-synthetic actions.
- Robot arm works can continue after LAN2 has been removed, but cold start-ups still need to be manually identified at the initial point, enabling energy to be activated through the configured body key, and then complete a non-motion handshake.

## Intent to submit

```text
docs: split single-gateway runtime and deployment planes
```
