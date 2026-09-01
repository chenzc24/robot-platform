# Validation of parallel links between PS2 chassis and local video relay

- Status:`completed`
- Responsible: Agent executes connection and program operations, user on-site supervision and operation of PS2 with entities
- Highest validation level:`L3`

## Objective

In the same cell phone hotspot, start and confirm the current PS2 control program for ESP32, while maintaining the MaixCam video relayed via computer FFmpeg/MediaMTX to the local port to verify that two links work in parallel, parking and end state.

## Initial state of the workspace

```text
## main...origin/main
 M .vscode/settings.json
```

`.vscode/settings.json` It's the user that's changed, and this goal is kept read-only. At the beginning, CLI displays MaixCam SSH, device RTSP and live video online, ESSP32 TCP 8266 is not available, and the whole is DEGRADED.

## Modifyable File

- `tools/esp32/webrepl_reset.py`
- `tools/esp32/webrepl_probe.py`
- `tests/dev/test_webrepl_reset.py`
- `plan/2026-09-01-ps2-video-joint-test/plan.md`
- `plan/log.md`

## Read-only files and directories

- `.vscode/settings.json`
- All version managed source codes, protocols, configurations and tools
- `ESP32/`, `Camera/`, `Robot Arm_Claws/`
- Local Secret, Device Backup and Cache
- MaixCam and ESP32 device file system

## Shared Dependencies

- The existing PS2/CAN program on the current ESP32 device and previous L3 failures, enabling, returning, R1 parking and final failure.
- `robot` CLI connection protection and current computer side video relay.
- Local Forward Peers `rtsp://127.0.0.1:8555/maixcam` And WebRTC page.

## Risk and safety door

- Risk: ESP32 program start or reset may initiate CAN and four-wheeler engines; PS2 input may create a real chassis movement; Wireless link interruption cannot replace physical stoppage.
- ESP32, PS2, CAN, chassis, MaixCam and computer video relay.
- User Operations: On-site control of physical stoppage, confirmation of chassis emptiness/restriction and safety area, implementation of default, low-speed small single-axis, return, parking and eventual failure, and observation of local video.
- Backup and recovery: device files are not uploaded or modified; USB is used to restore the channel when the ESS32 wireless failed, the device is maintained in case of video anomaly and only the computer relay is restarted.
- The movement confirms that before the PS2 program starts, the user must clearly confirm the person's location, stop, have no human barriers, the chassis is empty/limited, the arm of the machine is not involved and safe, action/stop/failure is understood.

## Expected work

1. Completion of L3 manual security clearance.
2. Read only the current ESP32 address and 8266 non-attainable reasons; Create a narrow WebREPL repositioning and PS2 diagnostic tool without reminiscing local evidence.
3. read PS2 original frame first; if necessary, with device end `finally` Automatic parking and disablement static `0.05 m/s`, `0.3 s` The direct pulse splits the validation chain, rebooting the existing PS2 program, authenticating the performance, single axis, returning, parking and failure.
4. Also forward port decode video from local RTSP and confirm continuous frames, resolution and frame.
5. At the end, confirm chassis failure, ESP32/video link status and unresolved matters.

## Validation

- L2: ESP32 found/8266, MaixCam RTSP, forward port and decode actual video.
- L1: Password segregation for WebREPL restoration tool, handshakes, hints and duplicates sending false object tests.
- L3: Users report PS2 failure, energy, small single axis, returning, parking and final failure.
- No robot arm action, no transfer or replacement of ESP32 program.
- `git diff --check`
- `git status --short --branch`

## Actual results

1. The user completes the L3 security clearance on this round, and at the end, confirms the chassis movement, parking and failure.
2. The current hot spot lease was restored after a short leak was detected by the ESS32 dynamic; `READY`.
3. Repeated decoded 120.047 seconds, received 2399 frames H.264 video, 1280 x 720, labelled with 20 fps, initial frame 1.5 seconds, no break or decode error.
4. Fixed PS2 probe to read mode `0x73`Marks `0x5A`, press key value 0, four axes 128/127, confirm hand handle power supply, connect and bottom read.
5. Agent sends fixed as authorized by user `vx=0.05 m/s`, 0.3 seconds straight-line pulse; with the device end of the same command `finally` Stopped and disabled, probe returned complete, user confirmed no problem with the action, certified the CAN and chassis call chain.
6. It's not CAN, PS2, or camera resources. WebREPL interrupted running through Ctrl-C when accessing MicroPython interpreter. `main.py`; the old diagnostic sequence sent back the car and two Ctrl-Cs, creating multiple residual hints and causing the command/response error. The old TCP session after the reset did not close with grace, resulting in the tool mischaracterizing the actual reset.
7. The tool is changed to a single Ctrl-C, command-by-command prompt sync, stationary probe, abnormal summary, motion security confirmation and separation feedback for "repeated commands sent/ whether the old patch is off". The compounding reason is changed from one to two, genuine confirmation `machine.reset()` It's actually been implemented; no more re-entry into REPL after re-entry, and users confirm that PS2 controls are back to normal.
8. (b) Not uploaded, overwrite or delete ESP32 device files, unoperated robot arm.

## Outstanding matters

- The old WebREPL TCP session may not be shut down until this machine is out of time when the ESPD32 is restarted; the tool returns correctly `disconnect_confirmed=false`, cannot judge the device not to be reset by the field alone.
- WebREPL is still the single-talk maintenance portal, and entering it interrupts the old chassis master; any diagnosis must be completed and the application must be reinstated and the validation operation avoided.
- This target is validated by the historical PS2 program on the device; the formal chassis service, the security heartbeat and the unified control protocol are still in line with the subsequent target.
- The ESP32 address is allocated by the Hotspot DHCP, still to be obtained by discovery or local coverage, without entering Git.

## Experience signal (for manual review)

This round repeats the fact that WebREPL's application is interrupted after entering the REPL, and that the TCP state after the repositioning does not represent the application state, constitutes an empirical signal that "the development channel must be clearly separated from the running channel"; it does not automatically create an experience document.

## Intent to submit

```text
test: verify PS2 control with local video relay
```
