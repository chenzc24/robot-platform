# Robot Platform

This project unifies development and control of an ESP32-S3 mobile chassis, a MaixCam vision system, and a Magician 6 robot arm in one VS Code workspace and, eventually, one computer-side control console.

## Current Architecture

- Computer: development, deployment, debugging, vision inference, logging, high-level task orchestration, direct ESP32 chassis control, and MaixCam arm/video control.
- MaixCam: video, vision capture, the robot-arm command/status endpoint, and the UART/TCP232 gateway to robot-arm LAN1. It no longer routes chassis commands.
- ESP32-S3: receives production chassis commands directly from the computer over a dedicated Wi-Fi/TCP runtime service and owns CAN, motors, sensors, heartbeat stop, and low-level safety. WebREPL remains maintenance-only.
- Robot arm: receives runtime commands on LAN1 through MaixCam and TCP232. LAN2 is reserved for computer maintenance, deployment, and teaching.
- Network: the computer, MaixCam, and ESP32 join the controlled LAN during normal operation. Robot-arm LAN1 remains behind MaixCam/TCP232, and LAN2 remains a maintenance path.

See the [overall plan](docs/overall-plan.md), [runtime baseline](docs/runtime/README.md), and [deployment baseline](docs/deployment/README.md).

Subsystem and operating documentation:

- [Offline runtime integration candidate](docs/integration/offline-runtime-candidate.md)
- [ESP32 MicroPython development](docs/esp32/development.md)
- [Computer-to-ESP32 chassis TCP link](docs/esp32/chassis-tcp.md)
- [Daily development session and troubleshooting](docs/development-session.md)
- [Shared runtime foundation](docs/runtime-foundation.md)
- [MaixCam-to-arm LAN1 diagnostics and controlled L3 validation](docs/robot-arm/lan1-diagnostic.md)

Use the flat CLI from the repository root for routine connection management:

```powershell
.\robot status
.\robot connect
.\robot details
.\robot disconnect
```

`connect` currently starts only a missing MaixCam video service or computer-side relay and reports ESP32 WebREPL as a maintenance check. It does not start the new ESP32 runtime service, deploy code, enter the ESP32 REPL, or reset a device. See [the development-session guide](docs/development-session.md) for maintenance commands and protection rules.

## Development Workflow

The project uses a bounded development loop:

```text
Goal plan → bounded implementation → L0-L4 validation → factual log → Git commit
```

- [Agent and collaborator rules](AGENTS.md)
- [Goal-planning method and template](plan/README.md)
- [Factual work log](plan/log.md)

Runtime code, device configuration, shared protocols, and real-device operations require a goal plan first. Real motion of one device is L3; coordinated motion across devices is L4. Both require explicit confirmation from an on-site person who can operate the physical emergency stop.

## Resource Management

These raw-resource directories remain local and are excluded from Git:

- `ESP32/`
- `Camera/`
- `Robot Arm_Claws/`

They contain vendor documentation, firmware, examples, and legacy code. Promote reviewed material into the version-controlled project structure instead of modifying the source archives directly.

## Planned Repository Structure

```text
robot-platform/
├── .vscode/       # VS Code tasks, debugging, and workspace configuration
├── config/        # Commit-safe configuration templates
├── docs/          # Architecture, protocol, deployment, and acceptance documents
├── protocol/      # Cross-device communication contracts
├── src/
│   ├── console/   # Computer-side unified console
│   ├── esp32/     # ESP32 chassis software
│   └── maixcam/   # Vision and gateway software
├── tests/         # Automated and integration tests
└── tools/         # Deployment, diagnostics, and device simulators
```

## Safety Principle

Every real-motion test requires on-site supervision and access to the physical emergency stop. Loss of the computer, Wi-Fi, SSH, WebREPL, or internet connection must lead to a locally defined safe state. Chassis stopping, arm limits, and device interlocks must not depend on a remote link.
