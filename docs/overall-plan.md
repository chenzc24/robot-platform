# Unified Robot Development and Control Plan

- Version: 1.1
- Baseline date: 2026-09-01
- Devices: ESP32-S3 chassis, MaixCam, Magician 6 robot arm, and development computer

## 1. Objectives

1. Move daily development, deployment, logs, and debugging into VS Code.
2. Build one computer-side console for chassis, vision, and robot-arm tasks.
3. Preserve local real-time control and safety when the computer or network fails.
4. Establish shared message, state, log, configuration, and test conventions.
5. Keep vendor resources read-only and manage promoted code through Git and GitHub.

## 2. Two-Plane Architecture

Detailed runtime and deployment rules are in [Runtime Baseline](runtime/README.md) and [Deployment Baseline](deployment/README.md).

### 2.1 Runtime Plane

```text
Computer: vision inference, task orchestration, unified console
                         │
                         │ Wi-Fi: video, commands, status
                         ▼
                   MaixCam gateway
              ┌──────────┴──────────┐
              │ UART2               │ UART0
              ▼                     ▼
           ESP32-S3              TCP232
              │ CAN                 │ wired TCP
              ▼                     ▼
            chassis          robot arm LAN1
```

Only the computer and MaixCam must join the runtime LAN. ESP32 does not depend on Wi-Fi, and arm LAN2 may be disconnected.

### 2.2 Deployment and Maintenance Plane

```text
ESP32:    computer → Wi-Fi/WebREPL; USB for initial setup and recovery
MaixCam:  computer → Wi-Fi/SSH/SCP; screen/USB virtual network for recovery
Robot arm: computer → wired LAN2 → DobotStudio Pro
TCP232:   computer → vendor configuration endpoint for one-time verification
```

Maintenance endpoints never become a second runtime control owner.

### 2.3 Responsibility Boundaries

| Node | Primary responsibilities | Exclusions |
|---|---|---|
| Computer | VS Code, deployment, vision inference, unified console, logs, task orchestration | No direct production commands to ESP32 or arm; not the final emergency stop or real-time interlock |
| MaixCam | Video, sole computer runtime endpoint, validation/routing, status aggregation, ESP32 and arm gateway | No unchecked motion pass-through; does not replace local safety |
| ESP32-S3 | UART runtime input, chassis motion, CAN, motors, sensors, heartbeat stop, status | No Wi-Fi runtime dependency; no arm control |
| TCP232 | Transparent UART-to-arm-LAN1 TCP transport | No application state machine |
| Robot arm | Motion execution, controller state, taught points, controller safety | No runtime dependency on hotspot or LAN2 |

## 3. Network Baseline

Development uses a controlled 2.4 GHz phone hotspot for the computer, ESP32, and MaixCam. Internet access is not required. Disable hotspot sleep and client isolation, use local configuration plus discovery instead of hard-coded DHCP addresses, and switch to a Windows hotspot, trusted LAN, or dedicated router only if stability requires it.

Robot-arm networks:

- LAN1: `192.168.5.1`, TCP service baseline `5200`, reached by TCP232.
- LAN2: `192.168.200.1`, used for DobotStudio maintenance; computer baseline `192.168.200.10/24` with no default gateway.
- Verify every address and TCP232 parameter before real-device integration.

Tailscale is not part of the first implementation. A future remote gateway may carry SSH, files, logs, video, and high-level discrete tasks, but never the only emergency stop, continuous chassis control, arm jogging, or low-level interlock.

See [Network Baseline](network/README.md) for detailed addressing, failure behavior, and acceptance checks.

## 4. Development Environment

`E:\Device Network` is the local repository root. `ESP32/`, `Camera/`, and `Robot Arm_Claws/` are ignored, read-only raw-resource archives. Production source lives under `src/esp32/`, `src/maixcam/`, and `src/console/`; the repository is the source of truth and devices are deployment targets.

### ESP32

- USB: initial firmware, Wi-Fi bootstrap, backup, and recovery.
- WebREPL: routine file synchronization and soft reset on a trusted development LAN.
- Production runtime: MaixCam-ESP32 UART, with velocity, stop, status, heartbeat, and fault handling.

### MaixCam

- Edit locally and deploy with standard SSH/SCP; MaixVision, MaixCode, and Remote-SSH are not required.
- Provide RTSP/H.264 video. FFmpeg remuxes without transcoding and MediaMTX exposes computer-side RTSP, HLS, and WebRTC.
- The unified service owns video, the computer command/status endpoint, both UART adapters, and aggregated status with explicit resource ownership.

### Robot Arm

- Keep DobotStudio Pro for teaching, configuration, project deployment, and maintenance through LAN2.
- Use MaixCam and LAN1 for runtime tasks.
- Validate protocols against a simulator before low-speed unloaded hardware tests.

## 5. Control and Data Flow

```text
Chassis: computer → Wi-Fi → MaixCam → UART → ESP32 → CAN/motors
Video:   MaixCam → Wi-Fi → computer vision and console
Arm:     computer → Wi-Fi → MaixCam → UART → TCP232 → LAN1
Status:  ESP32/arm → MaixCam → Wi-Fi → computer
```

MaixCam validates and converts device-specific commands and enforces cross-device gates such as requiring confirmed chassis stop before an arm task. ESP32 retains final limits, ownership, heartbeat, and stop behavior. The arm retains controller limits and body safety.

The first high-level task sequence is:

```text
chassis arrives → confirmed stop → vision detection → target validation
→ arm pick → result → arm safe pose → chassis may continue
```

## 6. Shared Message Contract

Replace legacy raw strings with a versioned envelope containing source, target, message type, sequence, timestamp, TTL, payload, and transport framing/CRC where needed. The common envelope does not make device command sets identical; MaixCam must parse and convert them.

Traceable results use `ACK`, `RUNNING`, `DONE`, `FAULT`, `REJECTED`, and `UNKNOWN`. Duplicate, expired, invalid, or unauthorized commands are rejected. Non-idempotent actions in `UNKNOWN` are not automatically retried.

Service-health state in `protocol/runtime-status.schema.json` remains distinct from physical task state. A service marked `running` does not mean the robot is moving.

## 7. Safety Requirements

- Every device powers on without motion.
- Loss of the computer, hotspot, or network must not allow new actions or continued stale velocity.
- Validate, limit, authorize, and log every motion command.
- ESP32 stops locally on heartbeat timeout and rejects invalid or expired commands.
- The arm uses confirmed safe poses, low speed, limited workspace, and conflict rejection during development.
- Do not move the arm until chassis stop is confirmed; do not allow high-speed chassis motion until the arm is safe.
- Software stop never replaces the physical emergency stop.

## 8. First Console Scope

- Link and device status for ESP32, MaixCam, and the arm.
- Chassis manual control, limits, and stop.
- Video, recognition results, and basic camera settings.
- Arm initialization, safe pose, and named actions.
- Sequence-aware command status, errors, and unified logs.
- Separate single-device debug and coordinated-task modes.

## 9. Implementation Stages

1. Repository and VS Code baseline.
2. Development network and independent deployment channels.
3. Shared protocol/simulators plus ESP32 and MaixCam resident services.
4. L2 connectivity and L3 low-speed single-device validation.
5. Unified console and L4 coordinated interlock validation.

Completed evidence as of 2026-09-01 includes ESP32 USB/WebREPL maintenance, PS2-CAN chassis operation, MaixCam SSH/SCP, continuous RTSP video, and MaixCam-UART-TCP232-arm LAN1 PING plus one fixed low-speed action. These facts do not prove the generic gateway, generic arm service, or coordinated system.

## 10. Frozen First-Version Decisions

1. Daily development uses VS Code.
2. The first development LAN is a 2.4 GHz phone hotspot.
3. ESP32 owns chassis control and low-level safety; its Wi-Fi is maintenance-only.
4. MaixCam is the sole computer-facing runtime node and gateway for ESP32 and the arm.
5. Arm LAN1 is for runtime control; LAN2 is for computer maintenance.
6. Tailscale is a possible future maintenance path, never a real-time safety link.
7. Raw vendor-resource directories are excluded from Git.

Update this document and obtain user confirmation before changing these decisions.
