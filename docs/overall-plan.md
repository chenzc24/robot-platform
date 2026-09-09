# Unified Robot Development and Control Plan

- Version: 1.2
- Baseline date: 2026-09-01
- Devices: ESP32-S3 chassis, MaixCam, Magician 6 robot arm, and development computer

## 1. Objectives

1. Move daily development, deployment, logs, and debugging into VS Code.
2. Build one computer-side console for chassis, vision, and robot-arm tasks.
3. Preserve local real-time control and safety when the computer or network fails.
4. Establish shared message, state, log, configuration, and test conventions.
5. Keep vendor resources read-only and manage promoted code through Git and GitHub.

## 2. Two-Plane Architecture

Detailed runtime and deployment rules are in [Runtime Baseline](runtime/README.md) and [Deployment Baseline](deployment/README.md). The current deployable offline candidate and machine-day gates are in [Offline Runtime Integration](integration/offline-runtime-candidate.md).

### 2.1 Runtime Plane

```text
Computer: vision inference, task orchestration, unified console
              ├── Wi-Fi/TCP: chassis commands/status ──→ ESP32-S3 ── CAN ──→ chassis
              │
              └── Wi-Fi: video and arm commands/status ─→ MaixCam
                                                            │ UART0
                                                            ▼
                                                          TCP232
                                                            │ wired TCP
                                                            ▼
                                                     robot arm LAN1
```

The computer, MaixCam, and ESP32 must join the runtime LAN. Arm LAN2 may be disconnected after the robot-arm project is deployed and started.

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
| Computer | VS Code, deployment, vision inference, unified console, logs, task orchestration, direct ESP32 chassis session, MaixCam arm/video session | No direct CAN or robot-arm LAN1 access; not the final emergency stop or real-time interlock |
| MaixCam | Video, vision capture, robot-arm validation/routing, arm status, UART0/TCP232 gateway | No chassis command routing; no unchecked arm pass-through; does not replace local safety |
| ESP32-S3 | Wi-Fi/TCP runtime input, chassis motion, CAN, motors, sensors, connection-health stop, status | WebREPL is not runtime control; no arm control |
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
- Production runtime: dedicated computer-to-ESP32 Wi-Fi/TCP service on the trusted LAN with one explicit session handshake, enable/disable, velocity, stop, status, health polling, and fault handling. WebREPL uses a separate maintenance port and lifecycle.

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
Chassis: computer → Wi-Fi/TCP → ESP32 → CAN/motors
Video:   MaixCam → Wi-Fi → computer vision and console
Arm:     computer → Wi-Fi → MaixCam → UART → TCP232 → LAN1
Status:  ESP32 → Wi-Fi/TCP → computer; arm → MaixCam → Wi-Fi → computer
```

The computer orchestrator combines independently reported chassis and arm state and enforces cross-device gates such as requiring confirmed chassis stop before an arm task. ESP32 validates chassis commands and retains final limits, session health, and stop behavior. MaixCam validates robot-arm tasks, and the arm retains controller limits and body safety.

The first high-level task sequence is:

```text
chassis arrives → confirmed stop → vision detection → target validation
→ arm pick → result → arm safe pose → chassis may continue
```

The unified PC drawing entry point accepts image or reviewed JSON input and
requires explicit selection of `baseline`, `localized_baseline`, or `advanced`.
`localized_baseline` remains the only production candidate: the PC commands a
bounded direct chassis displacement, confirms logical stop, and accepts only a
fresh one-dimensional AprilTag localization generation before resuming the
exact drawing checkpoint. `baseline` is an open-loop diagnostic and `advanced`
remains physically unvalidated. All share the same deployed ESP32, MaixCam and
robot-arm services, and a failed run never falls back to another strategy.
ESP32 owns every strategy's motor watchdog and stop behavior.

## 6. Shared Message Contract

Replace legacy raw strings with a versioned envelope containing source, target, message type, sequence, timestamp, TTL, payload, and transport framing/CRC where needed. The common envelope does not make device command sets identical; MaixCam must parse and convert them.

Traceable results use `ACK`, `RUNNING`, `DONE`, `FAULT`, `REJECTED`, and `UNKNOWN`. Duplicate, expired, invalid, or unauthorized commands are rejected. Non-idempotent actions in `UNKNOWN` are not automatically retried.

Service-health state in `protocol/runtime-status.schema.json` remains distinct from physical task state. A service marked `running` does not mean the robot is moving.

## 7. Safety Requirements

- Every device powers on without motion.
- Loss of the computer, hotspot, or network must not allow new actions or continued stale velocity.
- Validate, limit, authorize, and log every motion command.
- ESP32 stops locally when a velocity refresh expires, while an active attended
  session remains enabled. Connection-health timeout, link loss, or execution
  failure stops and disables. Invalid or expired commands are rejected without converting a healthy
  transport into a disconnect.
- The arm uses confirmed safe poses, low speed, limited workspace, and conflict rejection during development.
- Do not move the arm until chassis stop is confirmed; do not allow high-speed chassis motion until the arm is safe.
- Software stop never replaces the physical emergency stop.
- The attended chassis console and ESP32 both expose the defined 600 mm/s
  resultant planar and 800 mrad/s yaw command envelope, with lower startup
  slider selections. Combined motion remains scaled by the 200 RPM wheel cap.

## 8. First Console Scope

The primary implementation and control specification is the
[localhost robot console](console/control-console-ui.md). The browser is a thin
operator surface; its local Python process owns all device sessions and
protocol handling.

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

Completed evidence as of 2026-09-01 includes ESP32 USB/WebREPL maintenance, PS2-CAN chassis operation, a bounded direct computer-to-ESP32 TCP non-motion handshake, MaixCam SSH/SCP, continuous RTSP video, and MaixCam-UART-TCP232-arm LAN1 PING plus one fixed low-speed action. The attempted MaixCam-ESP32 UART downlink did not pass, and the user confirmed direct computer-to-ESP32 TCP as the replacement runtime boundary. The TCP proof covers only `HELLO`, `PING`, and `STATUS`; these facts do not yet prove the resident chassis motion service, generic arm service, or coordinated system.

Subsequent evidence as of 2026-09-03 advances that historical snapshot: the
[deployment record](deployment/2026-09-03-esp32-maixcam.md) documents ESP32 v3
publication and non-motion verification, MaixCam arm/video activation, and live
normalized arm joint/pose feedback. The shared PC client now uses a 5-second
query TTL. A subsequent attended drawing validation recorded four strokes / 282
arm commands at draw/travel/acceleration 15/5/5%,
followed by operator confirmation that the drawing was complete. This does not
validate a speed increase, precise TCP placement, cold-start reliability or L4
coordination. Fault-foundation protocol/recovery work remains a separate draft,
not part of this validated lineage. Architecture and safety boundaries above
are unchanged; see the runtime baseline for current source and evidence limits.

## 10. Frozen First-Version Decisions

1. Daily development uses VS Code.
2. The first development LAN is a 2.4 GHz phone hotspot.
3. ESP32 owns chassis control and low-level safety; its dedicated Wi-Fi/TCP service is the chassis runtime endpoint, while WebREPL is maintenance-only.
4. MaixCam is the computer-facing video and robot-arm gateway and does not route chassis commands.
5. Arm LAN1 is for runtime control; LAN2 is for computer maintenance.
6. Tailscale is a possible future maintenance path, never a real-time safety link.
7. Raw vendor-resource directories are excluded from Git.
8. The unified console may hold independent chassis and arm sessions, but each device still permits only one authorized runtime owner.

## 11. Manual Engineering Mode

For attended development, the robot arm supports an explicit YOLO/manual
engineering mode. This mode is independent of the chassis and permits the
computer API and Hardware console to issue repeatable relative jog commands for
J1-J6 and user-coordinate X/Y/Z. It does not use an application lease, one-use
token, repeated software enable, or chassis-idle interlock. Protocol framing,
numeric validation, sequence tracking, and error reporting remain active;
physical joint limits, collision protection, emergency stop, and recovery stay
with the Dobot controller. Coordinated production tasks remain a separate mode
and may add orchestration interlocks above these independent device APIs.

Update this document and obtain user confirmation before changing these decisions.
