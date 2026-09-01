# Offline Runtime Integration Candidate

## Scope

This candidate freezes the first runtime topology:

```text
computer ── RCP/TCP v2 ──> ESP32 ── CAN write ──> chassis
computer ── NDJSON ──> MaixCam ── RPA2/UART0/TCP232 ──> arm LAN1
MaixCam ── RTSP/H.264 ──> computer
```

MaixCam never carries chassis commands. LAN2 remains a robot-arm maintenance and deployment path.

## Resource Evidence Promoted into Code

| Source | Promoted fact | Candidate use |
|---|---|---|
| ESP32 `robot_config.py` in `CarControlCode.rar` | CAN0, 1 Mbps, TX8/RX18, motor IDs 1–4, wheel directions, 0.41 m geometry, 0.0635 m wheel radius | Existing `motor_bus.py` and `chassis_control.py`; not opened in L2 mode |
| ESP32 `motor_lib.py` | Extended CAN frame layout and speed-mode parameter writes | `MotorBus`; command writes only, no acknowledgement claim |
| Camera `chuankou.py` | `/dev/ttyS0`, `/dev/ttyS2`, UART2 A29/A28, 115200 | Arm endpoint uses only `/dev/ttyS0`, 115200 |
| Camera arm example `main.py` | `TCPCreate`, `TCPStart`, `TCPRead`, `TCPWrite`, LAN1 `192.168.5.1:5200`, `MovJ` | RPA2 arm project structure |
| Camera Flask example | MaixCam can host a computer-facing process | Candidate uses NDJSON/TCP, not the legacy HTTP button API |

Raw files remain read-only and excluded from Git.

## Explicit Blank Policy

`config/arm-policy.example.json` and `src/robot_arm/runtime/var.py` intentionally leave the safe initial pose, bounds, user/tool frames, payload, and gripper model empty. Empty is a deny condition: no `MOVEJ`, `MOVEL`, or `GRIPPER` request can execute.

The only committed arm operations are `PING` and `STATUS`. A future L3 goal may fill local, reviewed values and separately authorize one bounded motion round.

## Known Capability Gaps

| Gap | Current behavior | Not claimed |
|---|---|---|
| CAN feedback | `MotorBus` records successful local writes only | Motor receipt, wheel motion, physical stop |
| Arm terminal state | RPA2 `DONE` means its selected controller API returned without an observed error | Reached target pose, gripper closure, task success |
| Arm cancel | The endpoint reports `cancel_supported=false` | Network cancellation or a compensating move |
| Arm policy | Defaults reject all motion | Any safe range, load, tool, or initial pose |

`UNKNOWN` is terminal for a timed-out arm motion. The computer must inspect state instead of retrying.

## Deployment Sequence

1. Freeze a release manifest and local-test result.
2. Deploy ESP32 `tcp_v2_l2` only with local credentials, `motion_permitted=false`, and `NoMotionChassis`; verify authentication rejection, `PING`, `STATUS`, lease expiry, EOF, and port cleanup.
3. Deploy the arm project with `MOTION_ENABLED=false`; verify RPA2 `PING`, `STATUS`, and command rejection.
4. Deploy the MaixCam endpoint only through `run_arm_command_service.sh`, which verifies and releases the current launcher UART owner before starting, then restores the launcher supervisor on exit. Verify computer `arm.ping`, `arm.status`, UART restore, and no motion admission.
5. Keep the three results separate. No L3 motion or cross-device task is authorized by this candidate.

## Required Human Inputs Before L3

- Safe initial arm pose, joint/Cartesian bounds, tool/user frame, payload, gripper model and range.
- Confirmed controller API return, terminal-state, and stop/cancel semantics.
- Observed TCP232 configuration.
- Confirmed current ESP32 release and CAN feedback protocol, if it exists.

See [the machine-day runbook](machine-day-runbook.md) for the L2/L3 gates.
