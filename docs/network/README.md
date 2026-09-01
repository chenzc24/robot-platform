# Robot Platform Network Baseline

- Status: single-gateway runtime with separate deployment and maintenance paths
- Date: 2026-09-01
- Scope: computer, ESP32-S3, MaixCam, TCP232, and Magician 6 robot arm

This document defines network roles, addressing, failure behavior, and acceptance criteria. See the [overall plan](../overall-plan.md), [runtime baseline](../runtime/README.md), and [deployment baseline](../deployment/README.md).

## 1. Design Goals

1. Develop every subsystem from one VS Code workspace.
2. Use the existing phone hotspot first; a new router is not a prerequisite.
3. During normal operation, the computer connects only to MaixCam.
4. MaixCam uses local UART links to ESP32 and TCP232/arm LAN1.
5. Keep arm LAN2 as a separate wired maintenance path.
6. Keep stopping, limits, and critical interlocks local and independent of the computer, hotspot, Tailscale, or internet.

## 2. Topology

### Runtime

```text
computer ── Wi-Fi: video, commands, status ── MaixCam gateway
                                                   ├── UART2 ↔ ESP32 ↔ CAN ↔ chassis
                                                   └── UART0 ↔ TCP232 ↔ arm LAN1
```

Only the computer and MaixCam need the access point. The two downstream links do not traverse it.

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
| ESP32 Wi-Fi | Development hotspot | WebREPL deployment and diagnostics | Not a production runtime-control path |
| ESP32 UART | MaixCam UART2 | Chassis commands, heartbeat, and status | ESP32 stops locally on loss |
| MaixCam Wi-Fi | Controlled LAN | Sole computer runtime endpoint plus SSH/SCP | Business service is independent of SSH |
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
- Chassis runtime: computer → MaixCam → UART → ESP32 → CAN/motors.
- Arm runtime: computer → MaixCam → UART → TCP232 → wired TCP → arm LAN1.

UART protocols require framing, sequence, TTL, ACK/result semantics, timeout, and integrity checks. Video is observation and high-level input, never the only safety feedback.

## 6. Hotspot Requirements

- 2.4 GHz, fixed SSID, strong password stored only in ignored local configuration.
- Disable automatic shutdown and power-saving disconnects.
- Capacity for at least three clients during maintenance and two during runtime.
- No client isolation; the computer must reach MaixCam and, during maintenance, ESP32.
- Stable under screen lock, charging-state changes, and continuous video.

Internet/mobile data is optional. Address changes are normal and must be handled by discovery.

## 7. Development Channels

- ESP32: USB for initial configuration and recovery; WebREPL for routine synchronization and soft reset on a trusted development LAN. Close or restrict WebREPL for production operation.
- MaixCam: standard SSH/SCP for deployment, lifecycle, and logs; RTSP/H.264 for video. MaixVision and MaixCode are not dependencies.
- Robot arm: LAN1 only through the MaixCam gateway for runtime; LAN2 through DobotStudio for maintenance. The console must not bypass MaixCam and create a second owner.

## 8. Tailscale Boundary

Tailscale is not deployed in the first stage. A future MaixCam or subnet gateway may support SSH, files, logs, video, and high-level discrete tasks. Never use it as the only physical-stop path, for continuous chassis velocity/heartbeat, arm jogging, or low-level chassis-arm interlocks. ESP32 is not assumed to run Tailscale.

## 9. Failure Behavior

| Fault | Required behavior | Recovery |
|---|---|---|
| Hotspot loss | MaixCam accepts no new computer task; ESP32 stops under UART heartbeat rules | Rediscover, query actual state, explicitly reacquire ownership |
| Computer offline | No new commands from that session | Reconnect, query status, explicitly take control |
| ESP32 Wi-Fi loss | Maintenance only is affected; UART runtime state machine continues | Restore only when maintenance is needed; never restore old velocity |
| MaixCam-ESP32 UART loss | ESP32 stops; MaixCam rejects chassis-dependent tasks | Restore UART, perform non-motion handshake, reacquire ownership |
| MaixCam Wi-Fi loss | No new computer tasks; ESP32 stops by heartbeat policy | Query chassis and arm state before continuing |
| MaixCam-TCP232 loss | Gateway enters `FAULT` and rejects new arm tasks | Restore, discard expired queue entries, reinitialize |
| TCP232-arm loss | Gateway times out; action result may be `UNKNOWN` | Read actual arm state and obtain physical confirmation if needed |
| Arm LAN2 loss | Maintenance only is affected | Reconnect maintenance cable when required |

Never infer that an in-flight arm action stopped or completed after link loss. Mark it `UNKNOWN` or `FAULT` from actual evidence and block dependent actions.

## 10. First Connection Procedure

1. Start a fixed 2.4 GHz hotspot.
2. Connect the computer and record the current subnet.
3. Configure ESP32 Wi-Fi through USB and connect it for maintenance.
4. Configure MaixCam from its screen or recovery path and connect it.
5. Confirm both DHCP leases in the hotspot client list.
6. Test computer reachability to MaixCam and ESP32 maintenance endpoints without motion.
7. Test MaixCam SSH and ESP32 WebREPL.
8. In a separate device goal, test the MaixCam-ESP32 UART non-motion handshake.
9. Verify TCP232 settings and first test against an arm simulator.
10. Connect arm LAN1 and perform L2 non-motion status/PING.
11. Connect LAN2 only when DobotStudio maintenance is required.
12. Apply the AGENTS.md safety gate before any L3 motion.

## 11. Acceptance Criteria

- Runtime: computer and MaixCam remain connected, video and command/status channels are distinguishable, and rediscovery does not depend on an old DHCP lease.
- Development: ESP32 also joins the hotspot; USB recovery, WebREPL synchronization, MaixCam SSH/SCP, and ignored secret storage work.
- Arm: LAN1/LAN2 and TCP232 parameters are verified; the gateway detects connect, disconnect, timeout, and duplicate response; LAN2 maintenance is independent of LAN1 runtime.
- Safety: removing each critical link produces the documented safe or fault state.

Evidence recorded on 2026-09-01: MaixCam `/dev/ttyS0` through TCP232 to arm LAN1 passed versioned `PING/PONG` with sequence 1 and 163 ms round trip. Under a separately confirmed L3 safety gate, a fixed J1 +1°, one-second wait, -1° return at 5% speed/acceleration passed twice in 3525 ms and 3221 ms. This validates only that bounded diagnostic path, not a generic trajectory interface.

## 12. Alternative Access Points

Change the phone hotspot only for client isolation, repeated sleep/disconnect, insufficient client capacity, subnet conflict, or inadequate video/integration stability. Preferred order:

```text
phone hotspot → Windows hotspot → trusted existing LAN → dedicated small router
```

The access-point choice does not change the single-gateway runtime, MaixCam-ESP32 UART, arm LAN1/LAN2 roles, or local safety boundaries.
