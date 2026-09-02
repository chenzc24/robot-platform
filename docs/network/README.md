# Robot Platform Network Baseline

- Status: direct ESP32 chassis runtime plus MaixCam arm/video runtime, with separate maintenance paths
- Date: 2026-09-01
- Scope: computer, ESP32-S3, MaixCam, TCP232, and Magician 6 robot arm

This document defines network roles, addressing, failure behavior, and acceptance criteria. See the [overall plan](../overall-plan.md), [runtime baseline](../runtime/README.md), and [deployment baseline](../deployment/README.md).

## 1. Design Goals

1. Develop every subsystem from one VS Code workspace.
2. Use the existing phone hotspot first; a new router is not a prerequisite.
3. During normal operation, the computer connects directly to ESP32 for chassis control and to MaixCam for video and robot-arm control.
4. MaixCam uses UART0 only for TCP232/arm LAN1; it does not route chassis commands.
5. Keep arm LAN2 as a separate wired maintenance path.
6. Keep stopping, limits, and critical interlocks local and independent of the computer, hotspot, Tailscale, or internet.

## 2. Topology

### Runtime

```text
computer ── Wi-Fi/TCP: chassis commands/status ── ESP32 ↔ CAN ↔ chassis
    │
    └────── Wi-Fi: video and arm commands/status ── MaixCam ↔ UART0 ↔ TCP232 ↔ arm LAN1
```

The computer, ESP32, and MaixCam need the access point. Robot-arm LAN1 remains downstream of MaixCam/TCP232.

### Deployment and Maintenance

```text
computer ↔ hotspot ↔ ESP32 WebREPL
computer ↔ hotspot ↔ MaixCam SSH/SCP
computer ↔ wired LAN2 ↔ DobotStudio Pro / robot arm
computer ↔ TCP232 vendor configuration endpoint, only when verification is needed
```

## 3. Interface Responsibilities

| Interface | Connection | Purpose | Constraint |
|---|---|---|---|
| Computer Wi-Fi | Controlled LAN | Console, video, logs, deployment | Runtime loss triggers local safe behavior |
| Computer Ethernet | Arm LAN2 | DobotStudio, teaching, maintenance | Connect only for maintenance; no default gateway |
| ESP32 Wi-Fi runtime | Controlled LAN | Dedicated chassis TCP commands, health polling, and status | Independent of WebREPL; ESP32 stops locally on loss |
| ESP32 WebREPL | Controlled LAN | Deployment and diagnostics | Not a production runtime-control path |
| MaixCam Wi-Fi | Controlled LAN | Video, robot-arm endpoint, and SSH/SCP | Arm business service is independent of SSH |
| MaixCam UART0 | TCP232 UART | Arm commands and responses | Baseline 115200; verify before hardware use |
| TCP232 Ethernet | Arm LAN1 | Transparent UART/TCP conversion | TCP client to arm server |
| Arm LAN1 | TCP232 | Runtime control | Current baseline `192.168.5.1:5200` |
| Arm LAN2 | Computer | Maintenance and teaching | Fixed `192.168.200.1` |

## 4. Addressing

### Development Hotspot

The phone controls the subnet and DHCP leases. Do not assume a specific private subnet or permanently hard-code lease addresses. Discover devices in this order:

1. Explicit address in a Git-ignored `*.local.yaml` override.
2. Stable hostname or mDNS.
3. Bounded discovery on the current subnet.
4. Manual confirmation in the hotspot client list.

Use logical names such as `chassis-esp32`, `vision-maixcam`, and `arm-gateway`.

### Arm LAN1

| Device | Baseline | Role |
|---|---|---|
| Arm LAN1 | `192.168.5.1/24` | TCP server |
| Service port | `5200` | Arm application service |
| TCP232 Ethernet | suggested `192.168.5.7/24` | TCP client |

TCP232 baseline: UART transparent mode, 115200 baud, 8 data bits, 1 stop bit, no parity, TCP Client to `192.168.5.1:5200`. The suggested TCP232 address is not a claim about current device configuration.

### Arm LAN2

| Device | Address |
|---|---|
| Arm LAN2 | `192.168.200.1/24` |
| Computer Ethernet | `192.168.200.10/24` |

Leave gateway and DNS empty on the computer's LAN2 adapter. If the hotspot overlaps LAN1 or LAN2, change the hotspot or an explicitly authorized endpoint; do not depend on ambiguous routing.

## 5. Data Paths

- ESP32 deployment: VS Code → hotspot → WebREPL. This can interrupt `main.py` and is not runtime control.
- MaixCam deployment: VS Code → SSH/SCP → MaixCam.
- Video: MaixCam RTSP/H.264 → computer, optionally remuxed by FFmpeg and served by MediaMTX as local RTSP/HLS/WebRTC.
- Chassis runtime: computer → dedicated Wi-Fi/TCP service → ESP32 → CAN/motors.
- Arm runtime: computer → MaixCam → UART → TCP232 → wired TCP → arm LAN1.

Runtime protocols require framing, sequence, TTL, ACK/result semantics, and timeout. TCP supplies ordered integrity for chassis frames; the arm UART protocol still requires its own checksum. Video is observation and high-level input, never the only safety feedback.

## 6. Hotspot Requirements

- 2.4 GHz, fixed SSID, strong password stored only in ignored local configuration.
- Disable automatic shutdown and power-saving disconnects.
- Capacity for at least three clients during both maintenance and runtime.
- No client isolation; the computer must reach both MaixCam and ESP32 during runtime.
- Stable under screen lock, charging-state changes, and continuous video.

Internet/mobile data is optional. Address changes are normal and must be handled by discovery.

## 7. Development Channels

- ESP32: USB for initial configuration and recovery; WebREPL for routine synchronization and soft reset on a trusted development LAN. Close or restrict WebREPL for production operation.
- MaixCam: standard SSH/SCP for deployment, lifecycle, and logs; RTSP/H.264 for video. MaixVision and MaixCode are not dependencies.
- Robot arm: LAN1 only through the MaixCam gateway for runtime; LAN2 through DobotStudio for maintenance. The console must not bypass MaixCam and create a second arm owner.

## 8. Tailscale Boundary

Tailscale is not deployed in the first stage. A future MaixCam or subnet gateway may support SSH, files, logs, video, and high-level discrete tasks. Never use it as the only physical-stop path, for continuous chassis velocity, arm jogging, or low-level chassis-arm interlocks. ESP32 is not assumed to run Tailscale.

## 9. Failure Behavior

| Fault | Required behavior | Recovery |
|---|---|---|
| Hotspot loss | ESP32 stops under its local TCP heartbeat rule; MaixCam accepts no new arm task | Rediscover, query actual state, explicitly reacquire each owner |
| Computer offline | No new commands from that session | Reconnect, query status, explicitly take control |
| ESP32 Wi-Fi or TCP loss | ESP32 stops, clears its client and ownership, and retains safe state | Restore LAN, perform a fresh non-motion handshake, explicitly reacquire |
| MaixCam Wi-Fi loss | No new arm task; ESP32 direct chassis safety remains independent | Query arm state and reconnect MaixCam before continuing coordinated tasks |
| MaixCam-TCP232 loss | Gateway enters `FAULT` and rejects new arm tasks | Restore, discard expired queue entries, reinitialize |
| TCP232-arm loss | Gateway times out; action result may be `UNKNOWN` | Read actual arm state and obtain physical confirmation if needed |
| Arm LAN2 loss | Maintenance only is affected | Reconnect maintenance cable when required |

Never infer that an in-flight arm action stopped or completed after link loss. Mark it `UNKNOWN` or `FAULT` from actual evidence and block dependent actions.

## 10. First Connection Procedure

1. Start a fixed 2.4 GHz hotspot.
2. Connect the computer and record the current subnet.
3. Configure ESP32 Wi-Fi through USB and connect it for maintenance and the dedicated runtime service.
4. Configure MaixCam from its screen or recovery path and connect it.
5. Confirm both DHCP leases in the hotspot client list.
6. Test computer reachability to MaixCam and both ESP32 endpoints without motion.
7. Test MaixCam SSH and ESP32 WebREPL.
8. In a separate device goal, test the computer-ESP32 TCP non-motion handshake without entering WebREPL concurrently.
9. Verify TCP232 settings and first test against an arm simulator.
10. Connect arm LAN1 and perform L2 non-motion status/PING.
11. Connect LAN2 only when DobotStudio maintenance is required.
12. Apply the AGENTS.md safety gate before any L3 motion.

## 11. Acceptance Criteria

- Runtime: computer, ESP32, and MaixCam remain connected; chassis, arm, video, and maintenance channels are distinguishable; rediscovery does not depend on an old DHCP lease.
- Development: ESP32 also joins the hotspot; USB recovery, WebREPL synchronization, MaixCam SSH/SCP, and ignored secret storage work.
- Arm: LAN1/LAN2 and TCP232 parameters are verified; the gateway detects connect, disconnect, timeout, and duplicate response; LAN2 maintenance is independent of LAN1 runtime.
- Safety: removing each critical link produces the documented safe or fault state.

Evidence recorded on 2026-09-01: MaixCam `/dev/ttyS0` through TCP232 to arm LAN1 passed versioned `PING/PONG` with sequence 1 and 163 ms round trip. Under a separately confirmed L3 safety gate, a fixed J1 +1°, one-second wait, -1° return at 5% speed/acceleration passed twice in 3525 ms and 3221 ms. This validates only that bounded diagnostic path, not a generic trajectory interface.

## 12. Alternative Access Points

Change the phone hotspot only for client isolation, repeated sleep/disconnect, insufficient client capacity, subnet conflict, or inadequate video/integration stability. Preferred order:

```text
phone hotspot → Windows hotspot → trusted existing LAN → dedicated small router
```

The access-point choice does not change direct computer-ESP32 chassis ownership, MaixCam arm/video responsibilities, arm LAN1/LAN2 roles, or local safety boundaries.
