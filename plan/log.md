# Project maintenance log

The log only records the maintenance of projects that have occurred. Reusable experience is not an automatic tailing, but is only extracted separately when the user so specifically requests.

entry format:

```text
## YYYY-MM-DD - Destination Name

- Target: What to do with this job.
- Modify area: actually modified files, directories or subsystems.
- Validation: Physically executed inspection and highest level
- Hardware: Whether to connect, write or drive real devices.
- Submission status: Not submitted, submitted, pushed or blocked.
- Follow-up: remaining issues or next goal
```

## 2026-08-31 - Establishment of integrated robotic development and control repository

- Objective: To establish a private GitHub repository and record the overall programme of the ESP32 chassis, MaixCam visual and Magician 6 robot arm.
- Modify Area:`.gitignore`, `.gitattributes`, `README.md`, `docs/overall-plan.md`.
- Verify: L0; confirm that three directories and temporary directories were ignored by Git, check the temporary files, text formats, remote visibility and branch synchronization.
- Hardware: Unconnected, written or driven real device.
- Submission status: Submitted and delivered `main`,Submitted as `619190e` and `fa8da6a`.
- Follow-up: establishment of an environmental baseline for VS Code development.

## 2026-08-31 - Introduction of robotic project work streams Nuclear

- Objective: To introduce a streamlined and customized plan - implement - validate - logs - to submit workstreams, and to incorporate robotic hardware security constraints.
- Modify Area:`AGENTS.md`, `README.md` and `plan/`.
- Validation: L0; checking text discrepancies, key rules, neglect status and submission range.
- Hardware: Unconnected, written or driven real device.
- Submission status: This record will be sent as the target is submitted `main`.
- Follow-up: "VS Code develops an environmental baseline" as the first development objective using a new template.

## 2026-08-31 - Collating Web Program Documents

- Target: Write cell phone hotspots, device interfaces, robot arm double access, remote access to borders and network acceptance methods into independent network files.
- Modify Area:`docs/network/README.md`, `docs/overall-plan.md` and target plan
- Validation: L0; check key network decisions, relative links, Git format and submission range.
- Hardware: Unconnected, written or driven real device.
- Submission status: This record will be sent as the target is submitted `main`.
- Follow-up: Completion of IP and TCP 232 confirmations after physical device access and implementation of L2 inspection according to a web-based acceptance list.

## 2026-08-31 - Establishment of the ESP32 MicroPython development baseline

- Objective: To create a development environment for VS Code, Python 3.12, mpremote, esptool and the official WebREPL client without installation of ESP-IDF.
- Modify Area:`.vscode/`, `src/esp32/`, `docs/esp32/`, develop dependency, ignore rules, general catalogue description and target plan.
- Validation: L1; Validation of the host tool version, Python compilation, JSON configuration, official WebREPL client grammar and Git protection range.
- Hardware: Unconnected, written or driven real device.
- Submission status: This record will be sent as the target is submitted `main`.
- Follow-up: When the user connects to ESP32 USB, create L2 target to complete read-only recognition, file system backup, hotspot configuration and WebREPL wireless link validation.

## 2026-08-31 - Identification of ESP32 USB device

- Objective: To confirm the target device model only through COM7 without changing Flash or the file system.
- Modification area: Device targeting plan and maintenance log.
- Validation: L2; Users confirm that the site is safe and manually enters download mode.`esptool 5.3.1` Successfully identified ESP32-S3 QFN56 revision v. 0.2, 40 MHz crystal vibrates and 8 MB embedded PSRAM.
- Hardware: Connect to COM7; identify stubs only uploaded to RAM, unwieldy or burn Flash, and at the end the device is reset hard through RTS.
- Submission status: This record will be sent as the target is submitted `main`.
- Follow-up: Read the running time version and back up the device file system through MicroPython REPL, then configure cell phones hotspots and WebREPL.

## 2026-08-31 - Identify and backup ESP32 MicroPython Time

- Target: Read MicroPython version and file tree through COM7 and back up the existing file system without modifying the device.
- Modify area: ESP32 development document, VS Code file tree task, run-time backup target plan and maintenance log; local backup at Git ignore directory.
- Verify: L2; confirm MicroPython 1.27.0 with `ESP32_GENERIC_S3-SPIRAM_OCT`125684 bytes of 22 files, confirmed root directory and `SmartHybridChasisDemo/` 11 pairs of SHA-256 identical.
- Hardware: read running time and file systems through COM7;`mpremote`Stops the current program and softly resets into maintenance, does not upload, deletes or executes the movement code.
- Submission status: This record will be sent as the target is submitted `main`.
- Follow-up: Maintain the compound security condition, configure and run local hotspots through USB `webrepl_setup`Check the WebREPL on the hotspot.

## 2026-08-31 - Configure ESP32 hotspots and WebREPL

- Target: Allow ESP32-S3 on COM7 to automatically access 2.4 GHz hotspots after restart and develop computers from Windows for wireless maintenance via WebREPL.
- Modifications: ESP32 Web Launch Source Code and Secret Template, VS Code WebREPL portal, ESP32 Development Document, Target Scheme; True certificates are only stored in Git to ignore file and device file systems.
- Validation: L2; Validation of DHCP, ICMP, TCP 8266, WebREPL Rights, MicroPython version and read-only RESL probes after current sessions and hard-repeated sessions; and Checking through device end/local grammar, JSON, Secret Scan and Git format.
- Hardware: Write to ESP32 directories via COM7 `network_boot.py`, `secrets.py` and `boot.py`, and execute hard resets; without modification of the device's original chassis `main.py`, do not send a motion order, resume the start-up process after validation.
- Submission status: This record will be sent as the target is submitted `main`.
- (b) Separately audit and relocate the device's original chassis program;

## 2026-08-31 - Naughty and audit of ESP32 available bottom source Code

- Objective: To incorporate 11 existing chassis Python files from the ESP32 backup into Git and establish a pre-deployment security audit baseline without running hardware codes.
- Modify Area:`src/esp32/legacy/chassis_2026_08_31/` Byteshot, PathGit Properties, ESP32 Statistic Audit and Development Documents, Target Plan.
- Validation: L1; 11/11 consistent with read-only back-up SHA-256, all source-code static translation passed; false MotorBus validation speed limit and recapitulation of the state of the initial parking that is still writeable after a slow jump and failure; Secret scanning and Git format check passed.
- Hardware: not connected, write or drive real devices; no current changes `src/esp32/app/` Or device file systems.
- Submission status: This record will be sent as the target is submitted `main`.
- Follow-up: Selective migration from historical snapshots, first setting up default safe idle and motors stations and adding regression tests; prohibition of the full deployment of historical snapshots until the block item is resolved.

## 2026-08-31 - Verifying ESP32 PS2 True Control Access

- Target: Verify the current controls of the PS2 handle -- ESP32-CAN -- the 4-wheeler, parking and malfunctioning circuits, under empty chassis/limits and physical stopover conditions.
- Modification area: L3 test target plan and maintenance log; no changes to source code, configuration or device file system.
- (a) Validation: L3;
- Hardware: Connecting real ESP32, PS2 handles, CAN and chassis engines; motion triggered by live user handles, Agent did not send speed instructions, robot arm and other functions did not participate.
- Submission status: This record will be sent as the target is submitted `main`.
- Follow-up: This result only confirms that existing manual access is available; Continue to repair the default motion and electrical status block in L1 and do not expand the real machine test until the repairs are completed.

## 2026-08-31 - Establishment of ESP32 safe idle and chassis status machines

- Target: Without access to the real machine, repairing the unknown mode automobilization and failure in the historical audit is still writeable at speed, creating a testable formal chassis safety core.
- Modify Area:`src/esp32/app/` Security entrance, configuration templates and chassis status machines,`tests/esp32/` Fake MotorBus test, VS Code mission, ESP32 design/development/audit document and target plan.
- Validation: L1; 12 unit tests overwrite default `SAFE_IDLE`Python Static Compiler, JSON, Secret Scan and Git Format Check passed.
- Hardware: Unconnected, write or drive ESP32, CAN, electric or other real device; Historical real machine program remains unchanged.
- Submission status: This record will be sent as the target is submitted `main`.
- Follow-up: Migration and testing of the real MotorBus/CAN adapter and driver feedback, and migration of PS2 general controls and 250 ms lost parking; Non-deployment pending L1/L2.

## 2026-08-31 - Establishment of an ESP32 adapter Can

- Target: Selective migration of electrics from the freeze of historical snapshots to the CAN speed model protocol to create the official MotorBus that can be injected into the security chassis, and verify sending frames and failure rolls back.
- Modify Area:`src/esp32/app/motor_bus.py`, FakeCAN Test, ESS32 CAN/Safety/Development/Audit Documents and Target Plans.
- Validation: L1; 10 new FakeCAN tests and 12 existing chassis security tests have all passed, covering the extended ID, 8-bytes small-end load, speed limit, enabling zero before, after, after, after, after, after lot failure, and full rollback and status machine integration; Python static compilation, confidential scanning and Git format check passed.
- Hardware: Unconnected, write or drive ESP32, CAN, electric or other real device; Device still runs the historical PS2 program.
- Submission status: This record will be sent as the target is submitted `main`.
- Follow-up: confirm protocols and feedback frames with manufacturer information and establish L2 CAN connection checks that do not allow power generators to be inspected; and do not express sending success as a driver of execution until ACK and status read.

## 2026-08-31 - Establishment of the MaixCam wireless development channel

- Target: To connect MaixCam Pro to existing development hotspots, establish VS Code local editor, SSH diagnostics and SCP deployment channels without starting cameras, serials or motion links.
- Modify Area:`.vscode/tasks.json`, `docs/maixcam/`, `src/maixcam/`, `tests/maixcam/` target plan;user not submitted `.vscode/settings.json` Keep reading only.
- Validation: L2; Confirmation of device as Buildroot/riscv64, Python 3.11.0 and MaixCam library 1.24.0, completion of pre-writing backup of 872 files, dedicated key login, probe upload, SHA-256 consistency and JSON status read-back; Reconnection after short break of hot spots, complete route recovery.
- Hardware: Linking real MaixCam to hot spots; Not starting camera collection, not connecting or sending ESP 32, TCP 232, robot arm and chassis control command.
- Submission status: This record will be sent as the target is submitted `main`.
- Follow-up: Manual confirmation of MaixVision real-time images; additional target design visual services and two-way UART ownership, and implementation of corresponding L3/L4 security doors before any campaign validation.

## 2026-08-31 - Creation of a MaixCam-computer video link

- Objective: To create a primary RTSP/H264 output for MaixCam without relying on MaixVision, a direct computer detection and a follow-up console RTSP/HLS/WebRTC repeater layer.
- Modify Area:`src/maixcam/video/`, `tools/maixcam/`, `config/`, `tests/maixcam/`, VS Code, Development Dependence, MaixCam/Network/Overview Documentation and Target Plan.
- Validation: L2; Native RTSP decoded and snapped, FFmpeg `-c:v copy` Resealed RTSP restarts and decodes 592 frames, 1280 x 720, 20 fps; MediaMTX real bytes, HLS decodes and WebRTC pages can be accessed and the user then confirms that WebRTC actual video stream is normal.
- Hardware: Connect real MaixCam and open camera collection; no connection, configuration or drive ESP 32, TCP 232, robot arm or chassis.
- Submission status: This record will be sent as the target is submitted `main`.
- Follow-up: The user has confirmed that the image should rotate at 90 degrees in a clockwise fashion; and another target processing direction/marking, visual recognition and control desk integration.

## 2026-08-31 - Records Unified Development SessionSOP

- Objective: To organize ESP32 and MaixCam from dialogue into project operating documents for routine start-up, end-up, debarment, recovery and problem status.
- Modify Area:`docs/development-session.md`Project entrance, MaixCam video file, video acceptance plan and target record.
- Verify: L0; check document structure, link target, factual consistency, local address/private key leak and Git variance format.
- Hardware: Not connected, written or driven by any device; records only the actual facts and the user's manual acceptance results.
- Submission status: This record will be sent as the target is submitted `main`.
- Follow-up: Additional targets to improve the ESP32 wireless deployment, MaixCam camera ownership/restoration and visual orientation.

## 2026-08-31 - Create a running-time basis for modularized device

- Objective: To organize ESP32 and MaixCam into full English official source code, modular services, structured state, resource/control ownership and diagnostic VS Code entrance without access to real machines.
- Modify Area: Share `protocol/`ESP32 application, MaixCam video service, three sets of tests, development of validation tool, VS Code task, running time/overall/subsystem documentation and target plan; not submitted by user `.vscode/settings.json` Keep reading only.
- Validation: L1; Sharing protocol 4; ESSP 32 30; MaixCam 18 out of 52 tests; 18 official Python files without caches have passed and local secret/device overwhelming files, Bash syntax, PowerShell resolution, VS Code JSON, Status Schema, Source Language and Git format check passed.
- Hardware: Not connected, written, uploaded, duplicated or driven ESP 32, MaixCam, robot arm, TCP 232, CAN or motors; device continues to run its previously deployed version.
- Submission status: This record will be sent as the target is submitted `main`;only submitting target declaration paths, not including users `.vscode/settings.json`.
- Follow-up: Another L2 target-by-design verification of new module import, deployment, structured logs, video start-up and recovery; no loss of connection until the lease is controlled.

## 2026-09-01 - Establishment of flat connection management and maintenance of CLI

- Target: Compress ESP32, MaixCam and the daily connection of the computer video relay to single-layer connection protection and single-layer abnormal feedback, and provide protected status, log, stop, restart, kill and equip to restart the CLI entrance.
- Modified Area: Root Catalogue CLI Packer, Computer Connection Management and Command Entry, 16 Development Tool Tests, VS Code Tasks, Unified Development Sessions/Runtime Documents and Target Plans; Unsubmitted by Users `.vscode/settings.json` Keep reading only.
- Validation: L1 has passed a total of 68 tests, CLI code compiled, 46 VS Code missions JSON, official source language and Git format checked; L2 confirms ESP 32 8266, MaixCam SSH/RTSP, this machine RTSP/WebRTC is online, and the connection is 3.29 seconds back to READY, returning to READY after rebooting 6.76 seconds and de facto H264 decoded to 1280 x 720, 20 fps.
- Hardware: The missing MaixCam project RTSP was activated and the computer side FFmpeg/MediaMTX was restarted once; no login or repositioning ESP32, no uploading device code, no execution of MaixCam stop/strike/turn restart, no connection or drive chassis, CAN, TCP232 and robot arm.
- Submission status: This record will be sent as the target is submitted `main`;does not include users `.vscode/settings.json`, local device address, cache or log.
- Follow-up: Validation of MaixCam maintenance commands and cameras to restore boundary; Maintenance of ESP32 re-locking until deployment and L3 acceptance is completed when operating safely; Establishment of robot arm parameters and addition of connector adaptor.

## 2026-09-01 - Validation of PS2 chassis and video parallel links

- Target: Verify in the same hotspot that the ESP32 history PS2 chassis program works in parallel with MaixCam's live video transfer, and locates why PS2 was once unmanageable.
- Modified area: fixed WebREPL reposition/start/PS2 protected chassis probe, 7 ESP32 tool tests of 23 development tool tests, L3 target planning and maintenance logs; not submitted by users `.vscode/settings.json` Keep reading only.
- Validation: L2 confirms ESP32 WebREPL, MaixCam SSH, device RTSP and in-house relays are ultimately READY; This machine repeats 120.047 seconds to decode 2399 frames H.264 video, 1280 x 720, 20 fps, no breakout; L3 reads valid PS2 frames `0x73/0x5A`, execute device end automatic parking/deactivating `0.05 m/s`, 0.3 seconds of fixed pulse, confirmed by the user of PS2, motion, parking and failure.
- Hardware: Connecting the real ESP32, PS2, CAN, chassis motor and MaixCam; emptied the chassis and supervised by the user on site. Agent sent a low-speed pulse without the robot arm; no uploading or modification of the device file.
- Conclusion: not hardware or service occupation; WebREPL interrupted ESP32 `main.py`, the old multiple Ctrl-C caused the hints to be wrong, and the TCP conversation after the reset was not stymied and resulted in the misreporting. After the one interruption and the separation of the re-entry feedback, the re-entry cause was changed from one to two, and the PS2 link eventually recovered.
- Submission status: This record will be sent as the target is submitted `main`;does not include users `.vscode/settings.json`Local address, secret, cache or device log.
- (b) Continue to consider the historical PS2 process as a transitional realization until official security chassis services are deployed.

## 2026-09-01 - Break MaixCam to the machine arm LAN1 chain Road

- Goal: validate the frozen `MaixCam /dev/ttyS0 → PCB TCP232 → robot arm LAN1 192.168.5.1:5200` path, first with bidirectional non-motion diagnostics and then with one controlled low-speed return action.
- Modify Area:`protocol/arm-diagnostic-v1*`MaixCam robot arm gateway/L2/L3 probe and launcher resource protection, DobotStudio independent robot arm project, double-end testing, VS Code mission, robot arm/MaixCam/network file and target plan; not submitted by user `.vscode/settings.json` Keep reading only.
- Validation: L2 `PING/PONG` Serial number 1, 163 ms round-trip and no movement on robot arm; L3 fixed `STEP` With J1 heading 1°, waiting for 1 second, reverse 1°, speed/acceleration 5%, return both independent manual authorizations `DONE`It's 3525 milliseconds and 3221 milliseconds, and the user finally confirms that the link is connected.`/dev/ttyS0` Resume held by launcher.
- Security: STEP does not carry motion parameters, robot arm projects consume only once each time and MaixCam does not automatically retry; instead of having a direct re-run after the first user's omission, the project was stopped/recommenced manually and reauthorised. The entity stopped fast, the area was empty, the chassis was fixed, the position was secure, the low speed and load conditions were confirmed at the user's site.
- Local validation: protocol 10, ESSP 32 30, MaixCam 40, robot arm 7, development tool 23, 110 passed; 31 Python source files, 52 VS Code missions, JSON, Bash syntax, work area and Git format check passed.
- Hardware: Connecting real MaixCam, TCP232 and Magician E6; Computer LAN2 for DobotStudio maintenance only. Robot arm IP, TCP232 parameters, security parameters, instructional points, ESSP32, chassis or video services are not performed.
- Submission status: This record will be sent as the target is submitted `target/maixcam-arm-l2`;does not include users `.vscode/settings.json`Secret, device backup, cache or source.
- (b) Do not extend the fixed STEP to any physical entry until the status query, semantics and malfunctions are restored.

## 2026-09-01 - Verifying robot arm without LAN2 operating path

- Target: Distinguishing the reliance of robot arm work on the data link during the running period, verifying whether RPA 1 can still be diagnosed and controlled by MaixCam through UART/TCP232 and robot arm LAN1.
- Modify area: add only this target plan and add a fact log; not submitted by the user`.vscode/settings.json`Keep reading only.
- Validation: No old LAN2 protocol for the first time`Initialize`Not in 2 seconds.`yunxing`No action; follow-up confirmation that RPA1 is not using the old protocol. Users are not moving when connecting to LAN2 after the RPA1 has been activated by LAN2`PING`It's about 326 milliseconds back and forth;`PING`Still successful and moving to and from 194 milliseconds. Following the confirmed L3 safe door, Agent is sending a fixed STEP one degree, J1 is waiting one second, returning to 1 degree, speed/acceleration 5%; robot arm is returning successfully and recovering in 3201 milliseconds`ready`, user confirm action is normal.
- Hardware: Real MaixCam, TCP232 and robot arm involvement; Ultimately, PING and STEP were completed after the physical removal of LAN2. After the test exit, the serial was restored to launcher and the single temporary probe was removed from MaixCam and locally; No modification of the product program, robot arm engineering, TCP232 configuration, ESP32 or chassis.
- Conclusion: LAN2 is used only for start-up, maintenance and diagnosis of robot arm works, without carrying RPA1 operational period control; RPA1 can remove the LAN2, MaixCam-TCP232-LAN1 link once it is in operation. The ability of a cold start/entity enabler to initiate RPA1 automatically remains unverified, and each re-electrication of a robot arm must be initiated through LAN2 and confirmed without motion PING before the configuration automatically starts.
- Submission status: This record will be sent as the target is submitted`target/maixcam-arm-l2`;does not include users`.vscode/settings.json`Secret, cache or source.
- Additional target survey and validation of RPA1 startup; do not mix old`Initialize`/`biao`The protocol and the RPA1 diagnostic protocol do not extrapolate this fixed STEP result to a generic action interface or a broken chain restoration capability.

## 2026-09-01 - Freezing MaixCam single gateway operation and independent deployment to maintain double plane

- Target: Only MaixCam, MaixCam, will be connected to the computer when it is running, and the ESP32 chassis and TCP232/mechanic arm structure will be centrally controlled by UART on both tracks, and the three-end deployment route will be formally written into the project baseline with the computer.
- Modify Area:`AGENTS.md`, project portal, overall scheme, network scheme, add running time and deployment maintenance documents and target plans; not submitted by users`.vscode/settings.json`Keep reading only.
- Validation: L0; double-platform expansion, role, control path, state feedback, consistent cross-check of failure behaviour and execution sequence, all new local links exist, secret/IP check and Git format check passed.
- Hardware: Unconnected, written, duplicated or driven ESP 32, MaixCam, TCP 232, robot arm, CAN, electric or camera; record only previously confirmed real facts.
- Conclusion: production runtime commands follow `computer → MaixCam → ESP32/robot arm`. ESP32 Wi-Fi, MaixCam SSH/SCP, and robot arm LAN2 belong to the maintenance plane and do not create a second runtime owner.
- Submission status: This record will be sent as the target is submitted`target/single-gateway-runtime-deployment`;does not include users`.vscode/settings.json`Secret, device backup, cache or source.
- The next goal is to define shared message shell, state semantics, simulators and test vectors, followed by ESP32 UART service, MaixCam gateway, robot arm general service and computer client; L2/L3/L4 is certified on a risk-by-risk basis.

## 2026-09-01 - Convert repository documentation to English

- Goal: make every Git-managed Markdown document English-only, including active architecture and subsystem documentation, collaboration rules, historical plans, and the factual log.
- Modified scope: all tracked Markdown files plus the new English-migration goal plan; `.vscode/settings.json` remained user-owned, read-only, and unstaged.
- Method: core architecture and safety documents were manually rewritten; a local offline model provided a first pass for historical records and secondary documents, followed by terminology normalization and structural checks. No repository content was sent to an external translation service.
- Validation: L0; zero CJK and Unicode replacement characters, all relative links resolve, fenced code blocks are balanced, secret-pattern and address review is clean, and Git diff-format checks pass.
- Hardware: no device was connected, written, reset, or moved. No source code, protocol schema, device configuration, backup, or raw-resource archive changed.
- Commit status: this record is committed and pushed with `target/english-only-documentation`; the commit excludes user settings, credentials, caches, backups, and raw resources.
- Follow-up: future edits should keep Markdown documentation in English. Historical records may receive style-only copy editing, but their factual outcomes must not change.

## 2026-09-01 - Establish the direct computer-to-ESP32 TCP runtime foundation

- Goal: replace the failed MaixCam-to-ESP32 UART runtime boundary with a direct computer-to-ESP32 Wi-Fi/TCP chassis endpoint and prove a bounded application-level link without motion.
- Modified scope: architecture entry points and active runtime/network/deployment/subsystem documents; RCP1/TCP v1 codec, vectors, ESP32 responder/probe, computer client/probe, tests, workspace validation, and this goal record. The user-owned `.vscode/settings.json` remained read-only and unstaged.
- Local validation: 16 protocol, 39 ESP32, 6 console, 23 development-tool, 40 MaixCam, and 7 robot-arm tests passed, for 131 total. Python syntax, workspace policy, JSON, Markdown relative links, changed-scope English, secret review, and Git diff formatting passed.
- Hardware validation: after the user confirmed the current L3 safety gate, the legacy chassis instance was interrupted and disabled. Three isolated non-startup files were uploaded and verified byte-for-byte. One real TCP session returned `WELCOME`, `PONG`, and `STATE` for sequences `1,2,3`; both ends reported three handled requests, safe idle, motion disabled, and complete.
- Safety and restoration: no motion/CAN/MotorBus command was sent. The one-client server exited, a protected reset was sent, WebREPL returned online, and the temporary runtime port was closed. The reset socket did not confirm closure before its timeout, and PS2 operation after reset was not exercised.
- Commit status: committed on `target/computer-esp32-tcp-runtime` and synchronized with its origin branch; the commit excludes user settings, credentials, caches, backups, and raw resources.
- Follow-up: implement authenticated ownership, heartbeat-driven local stop, bounded chassis commands, CAN composition, resident startup, and reconnect behavior under a separate L3 goal before claiming production chassis control.

## 2026-09-01 - Integrate direct chassis motion over RCP/TCP v2

- Goal: replace the superseded MaixCam-to-ESP32 UART motion route with a local direct computer-to-ESP32 TCP motion foundation while retaining MaixCam as the video and robot-arm gateway.
- Modified scope: new RCP/TCP v2 contract/codec/vectors, injected ESP32 motion service and connection runtime, non-retrying computer client, flat dual-session router, 26 tests, three runtime documents, and the isolated goal plan/log.
- Parallel ownership: work ran in `E:\Device Network - direct-chassis-motion` from the real-device-validated commit `344a428`. The primary worktree, user `.vscode/settings.json`, `target/motion-services-v1`, device files, and raw resources remained read-only and unstaged.
- Validation: L1; 157 repository tests passed (14 console, 23 development, 51 ESP32, 40 MaixCam, 22 protocol, and 7 robot-arm), all 73 repository Python files compiled, JSON and workspace checks passed, Markdown links resolved, formal source remained ASCII, and secret/unsafe-default/diff checks passed.
- Safety: v2 defaults to no credential verifier and `motion_permitted=false`; malformed authenticated input, disconnect, short write, execution failure, hold expiry, and lease expiry attempt both stop and disable; identical duplicates replay cached responses without re-execution; unknown state-changing outcomes are never automatically retried.
- Hardware: no device, real socket, Wi-Fi session, WebREPL, CAN, motor, MaixCam process, TCP232, robot API, deployment target, or local credential was accessed or changed.
- Commit status: implementation commit `96371b7` was committed and pushed on `target/direct-chassis-motion-v2`; this factual status update follows as a log-only commit.
- Follow-up: implement a bounded listener and ignored local credential loading, deploy v2 with motion and CAN disabled for L2, then create a separate on-site L3 goal for reviewed CAN composition, heartbeat stopping, and low-speed motion. Integrate the arm-only MaixCam session separately.

## 2026-09-01 - Build the offline runtime integration candidate

- Goal: turn resource-backed ESP32, MaixCam, and arm facts into one locally tested candidate while preserving direct computer-to-ESP32 chassis control and the separate computer-to-MaixCam-to-arm route.
- Modified scope: added the computer/MaixCam NDJSON envelope, RPA2 framing and vectors, the MaixCam arm endpoint/client/simulator/UART restoration launcher, a default-deny DobotStudio LAN1 project, an ESP32 no-CAN v2 listener composition, local configuration/release templates, tests, and linked architecture/deployment/runbook documentation. Raw resources, the primary worktree, user-owned `.vscode/settings.json`, device state, credentials, and all hardware remained untouched.
- Resource evidence: the ESP32 archive supplied the CAN wiring, motor mapping, speed-mode frame format, and mecanum geometry; Camera examples supplied MaixCam UART devices and the arm LAN1 TCP server shape. These facts are preserved as evidence, not copied raw archives.
- Safety: ESP32 `tcp_v2_l2` composes `NoMotionChassis`, with `motion_permitted=false` and no CAN construction. The arm project has `MOTION_ENABLED=false` and null policy bounds; MaixCam motion admission is false by default. Unknown arm outcomes are never retried. CAN acknowledgement, physical feedback, arm terminal position, and network cancellation are declared unavailable.
- Validation: L1; 172 local tests passed (28 protocol, 52 ESP32, 44 MaixCam, 9 robot arm, 16 console, 23 development tools). Selected sources compiled; JSON, local links, English-only changed documentation, secret review, workspace validation, shell syntax, and diff formatting passed.
- Hardware: no device, process, endpoint, credential, file upload, CAN bus, TCP232, arm controller, video service, or motion system was accessed or changed.
- Commit status: implementation commit `d501a2f` was committed and pushed on `target/offline-runtime-integration`; this factual submission update follows as a log-only commit. User settings, secrets, caches, backups, and raw resources are excluded.
- Follow-up: deploy each endpoint only in its default-deny L2 mode, capture rollback/readback evidence, then create a new L3 goal after the arm policy and controller terminal/cancel semantics are known.

## 2026-09-01 - Define the unified control console UI

- Goal: define an implementation-ready modern desktop console for camera preview and future overlays, direct ESP32 chassis control, MaixCam-routed robot-arm control, command evidence, and persistent fault handling.
- Modified scope: added `docs/console/control-console-ui.md`, linked it from the README and overall plan, and added this isolated goal plan/log. Runtime code, protocols, tests, configuration, raw resources, credentials, and all other worktrees remained read-only.
- Design result: the reference layout gives video the dominant left workspace, stacks independent chassis and arm panels on the right, and places the command journal and active faults across the bottom. It binds only currently available candidate calls, labels unavailable physical feedback explicitly, and keeps hardware motion locked.
- Validation: L0; the workspace validator reported no errors, changed Markdown is English-only, relative links resolve, the interactive mockup was rendered and inspected at desktop and narrow widths, and Git diff formatting passed.
- Hardware: no device, socket, local relay, credential, process, deployment target, CAN bus, motor, TCP232, or robot-arm API was accessed or changed.
- Commit status: intended for `target/control-console-ui-design`; the in-conversation mockup remains outside the repository, while the durable design specification is version controlled.
- Follow-up: obtain user approval for the layout and five explicit UI decisions, then implement the PySide6 shell, simulator adapters, state store, worker wrappers, and PyAV video path under a separate L1 goal.

## 2026-09-01 - Implement the simulator control console shell

- Goal: deliver the first runnable local desktop control-console implementation without real device access, transport, or motion.
- Modified scope: added PySide6 as a development dependency; added `src/console/ui/` models, controller, views, and module entry point; added seven console tests; documented the Phase A launch boundary; updated the UI design status; and added this goal plan/log. Existing runtime clients, protocols, device source, configuration, raw resources, credentials, and every device filesystem remained read-only.
- Implementation: the desktop shell provides the video-first layout, overlay-ready placeholder, independent simulator chassis and arm panels, press-and-hold chassis controls, arm joint/Cartesian/gripper forms, command lifecycle journal, persistent faults, fault acknowledgement/recheck, simulator fault scenarios, and a responsive compact control-tab layout. Hardware mode clears state and rejects every action because no adapter is present.
- Validation: L1; 179 tests passed across console (23), development (23), ESP32 (52), MaixCam (44), protocol (28), and robot-arm (9) suites. The offscreen UI smoke test, Python compilation, workspace validation, source ASCII review, and Git format checks passed. Native previews were inspected at 1440 x 900 and 1280 x 720.
- Hardware: no device, network endpoint, socket, video relay, MediaMTX process, SSH/WebREPL session, deployment target, CAN bus, motor, TCP232, or robot-arm API was accessed, changed, or moved.
- Commit status: intended for `target/control-console-ui-phase-a`; no secret, local configuration, cache, screenshot, or raw resource is staged.
- Follow-up: Phase B adds worker-thread adapters for the existing chassis and MaixCam arm clients plus decoded RTSP video. That work must first preserve the current default-deny and no-automatic-retry semantics, then pass local L1 and separate L2 evidence before any motion stage.

## 2026-09-01 - Add the control console Phase B runtime foundation

- Goal: add locally tested computer-side runtime adapters to the unified PySide6 console while preserving default-deny hardware motion behavior.
- Modified scope: ignored secret-free console configuration template; console runtime configuration, serialized ESP32/MaixCam-arm sessions, PyAV frame worker, controller/view wiring, local tests, console documentation, and this goal plan/log. Existing protocol clients, device source, raw-resource archives, user settings, local configuration, and device state remained read-only.
- Implementation: each control client has an independent FIFO background owner and only explicit connection, `PING`/`STATUS`, disconnect, and shutdown are admitted. All state-changing command names are rejected before dispatch and are never retried. The RTSP worker copies RGB frames into Qt-owned images and can write an explicitly configured local snapshot. Hardware-mode UI binds only configuration-gated connection, status, preview, fault, and disconnect paths; lease, enable, velocity, arm primitives, and chassis software stop remain disabled or rejected.
- Validation: L1; 184 tests passed across console (28), development (23), ESP32 (52), MaixCam (44), protocol (28), and robot arm (9). The offscreen console smoke test, workspace validation, source ASCII audit, and Git diff-format validation passed. Fake clients and a fake decoder covered the new paths; no test contacted a network endpoint or imported a real stream.
- Hardware: no device, endpoint, socket, RTSP stream, relay, credential, process, deployment target, CAN bus, motor, TCP232, or robot-arm API was accessed, written, reset, or moved.
- Commit status: committed and pushed on `target/control-console-ui-phase-b`; local configuration, credentials, caches, backups, raw resources, and user settings are excluded.
- Follow-up: create a separate L2 goal only after the user provides approved local endpoint configuration and asks for non-motion connection/status validation. Motion admission, heartbeat scheduling, bounded polling, and L3/L4 safety work remain separate.

## 2026-09-01 - Harden local console state and worker behavior

- Goal: finish the requested L1 hardening without a local endpoint simulator: strict status parsing, video/session failure coverage, and hardware-mode UI binding checks.
- Modified scope: console status mapper, models, controller, runtime worker lifecycle, views, local console tests, console documentation, and this goal plan/log. The primary worktree's user-owned `.vscode/settings.json`, local configuration, protocol source, device source, raw archives, credentials, endpoints, relays, and device state remained read-only.
- Implementation: the console now accepts only full RCP/TCP v2 chassis `STATE` frames and terminal MaixCam `arm.status` lifecycle responses carrying the current RPA2 service state. Malformed status retains the last known display state and raises a persistent fault. Safe-query errors close the affected session without retry. Decoder shutdown reports a bounded degraded fault when it cannot stop; snapshots cannot escape the local `logs/` root. Hardware mode continues to reject all motion while displaying copied decoded frames and exact reported non-motion state.
- Validation: L1; 190 local tests passed (console 34, development 23, ESP32 52, MaixCam 44, protocol 28, robot arm 9), plus offscreen UI smoke test, workspace validation, ASCII audit, and Git diff-format validation. Tests use only fake clients, fake frame containers, temporary local files, and offscreen Qt.
- Hardware: no device, endpoint, socket, RTSP stream, relay, credential, process, deployment target, CAN bus, motor, TCP232, or robot-arm API was accessed, written, reset, or moved.
- Commit status: committed and pushed on `target/control-console-ui-phase-b-hardening`; user settings, secrets, caches, backups, local configuration, and raw resources are excluded.
- Follow-up: L2 must validate the actual endpoint response and timeout/reconnect behavior with motion disabled. L3 remains a separate on-site safety-governed motion goal.

## 2026-09-02 - Deploy and validate the resident ESP32 RCP/TCP v2 L2 listener

- Goal: deploy the reviewed no-motion ESP32 listener, make its safe startup
  resident, and validate the real computer-to-ESP32 console path without
  motion.
- Modified scope: the version-controlled ESP32 boot entry point, a non-secret
  L2 device configuration template, one deployment evidence document, and this
  goal plan/log. The primary worktree's user-owned `.vscode/settings.json`, raw
  resource archives, MaixCam services, arm project, TCP232 settings, CAN, and
  motion source remained untouched.
- Deployment and recovery: after the user confirmed the on-site transition
  safety gate, the previous root launcher and support files were backed up into
  an ignored local directory. The reviewed L2 files and a generated local
  credential were uploaded over COM7; source/readback hashes matched for the
  runtime file set. A first credential generation error produced a too-short
  value and was corrected before application traffic. The new boot entry point
  then restored the network and invoked only the no-motion application entry
  point. No flash erase, firmware write, CAN construction, motor call, or
  motion command occurred.
- Hardware validation: L2. The resident listener accepted a connection after
  reset. Valid `HELLO`, `PING`, and `STATUS` returned `WELCOME`, `PONG`, and
  `STATE` with `ready`/`disabled`, `motion_permitted=false`, and no lease.
  A valid-format wrong credential returned `authentication_failed`; a later
  valid session reconnected and queried status. The actual console runtime
  completed `connect -> status -> disconnect`. No state-changing request was
  sent.
- MaixCam status: the reachable SSH port still required host-key trust, while
  the observed RTSP and arm-service ports were not listening. This goal did not
  authorize starting, stopping, or configuring MaixCam services, so video and
  arm L2 validation remain separate pending work.
- Validation: 190 tests passed when the six subsystem suites ran in isolated
  Python processes (ESP32 52, protocol 28, console 34, MaixCam 44, robot arm
  9, development tools 23); selected device-path tests also passed. Python
  compilation and the real L2 session above completed, and ignored
  credentials/backups/local configuration were confirmed excluded from Git.
  One monolithic `pytest` collection remains unsuitable: two historical
  modules named `chassis_tcp_probe` collide in Python's import cache depending
  on collection order. That shared test-runner issue was observed but not
  changed in this goal. Diff review and commit/push follow this record.

## 2026-09-02 - Validate guarded ESP32 CAN and one attended L3 chassis motion

- Goal: add an explicit L3 CAN composition to the resident direct ESP32
  RCP/TCP v2 service, deploy it first motion-locked, then verify one
  low-speed, duration-bounded wheel-rotation command under an on-site safety
  gate.
- Modified scope: ESP32 CAN construction/composition/startup source, local
  L3 configuration template, a bounded computer-side L3 tool, ESP32 fake-CAN
  tests, the L3 runbook, and this plan/log. The raw resource archives,
  credentials, firmware image, MaixCam, robot arm, TCP232, console source, and
  user settings remained untouched.
- Implementation: the L3 composition creates the legacy-confirmed ESP32 CAN
  peripheral only when `tcp_v2_l3` is selected, starts with zero-speed plus
  disable output, and composes `SafeMecanumChassis` with the authenticated
  v2 service. Motion stays false until an ignored local flag is explicitly
  enabled. The first runtime limits are 50 mm/s linear, 100 mrad/s angular,
  and 200 ms hold. The L3 test client requires explicit execution and safety
  flags; its setup lease and shorter renewed motion lease account for the
  four-motor initialization duration.
- Validation: L1, 56 ESP32 tests passed and the tool's no-execute dry run
  passed. L3, after the user twice confirmed the immediate on-site safety
  gate, a 14-file deployment matched device readback hashes. The motion-locked
  restart reported `ready`/`disabled` with no fault. The explicitly enabled
  restart then completed one attended forward 50 mm/s, 200 ms command while
  raised/restrained; the user observed normal brief wheel rotation. Final
  status was disabled with no active lease, hold, or fault. The first final
  release request found its setup lease already expired and was rejected only
  after the local stop/disable path; no movement was retried.
- Hardware limitations: CAN local send acceptance and the operator's
  observation are the only evidence. There is no driver ACK, wheel feedback,
  bus-off recovery, or controller fault telemetry. The device remains an L3
  attended-test configuration, not a general production release.
- Commit status: pending this target's diff review, commit, and push. No
  backup, secret, local configuration, or raw resource is staged.

## 2026-09-02 - Add the attended manual chassis debug panel

- Goal: bind the deployed direct ESP32 RCP/TCP v2 chassis lifecycle to the
  desktop console for explicit attended L3 debugging, while keeping Hardware
  mode default-deny and disconnected on launch.
- Modified scope: console local configuration template, runtime queue
  admission, controller/view bindings, console documentation, deterministic
  fake-client tests, and this goal plan/log. ESP32 source and device files,
  protocol source, MaixCam, arm source, credentials, raw archives, local
  configuration, and user settings remained read-only.
- Implementation: a local `manual_chassis.enabled` flag defaults to false.
  Only an ignored local override permits acquire, heartbeat, enable, velocity,
  stop, disable, and release. The UI requires explicit Connect, Acquire,
  Enable, and manual unlock; it bounds velocities, refreshes only while
  unlocked/held, coalesces periodic work, and prioritizes stop-like requests.
  Turning manual unlock off, releasing a direction, disconnecting, or a
  failed motion result clears the local hold state.
- Validation: L1. Console tests `36 passed`; ESP32 `56 passed`; protocol `28
  passed, 6 subtests passed`; MaixCam `44 passed`; robot arm `9 passed`; and
  development tooling `23 passed`. Offscreen UI smoke, Python compilation,
  and `git diff --check` passed. Tests used fakes/offscreen Qt and no endpoint
  access.
- Hardware: no device, socket, stream, credential, deployment operation, CAN
  bus, or motion command was accessed. A panel-to-device test remains L3 and
  requires a fresh immediate on-site safety confirmation.
- Commit status: committed and pushed on `target/control-console-manual-l3`;
  ignored local configuration and secrets are excluded.
- Follow-up: conduct one explicitly gated attended panel test, beginning with
  connect/status and then a separate low-speed hold-to-run movement; add
  physical feedback before treating `DONE` as wheel-motion evidence.
