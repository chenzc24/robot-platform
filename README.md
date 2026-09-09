# Robot Platform

This project unifies development and control of an ESP32-S3 mobile chassis, a MaixCam vision system, and a Magician 6 robot arm in one VS Code workspace and, eventually, one computer-side control console.

## Current Architecture

- Computer: development, deployment, debugging, vision inference, logging, high-level task orchestration, direct ESP32 chassis control, and MaixCam arm/video control.
- MaixCam: video, vision capture, the robot-arm command/status endpoint, and the UART/TCP232 gateway to robot-arm LAN1. It no longer routes chassis commands.
- ESP32-S3: receives production chassis commands directly from the computer over a dedicated Wi-Fi/TCP runtime service and owns CAN, motors, sensors, connection-health stop, and low-level safety. WebREPL remains maintenance-only.
- Robot arm: receives runtime commands on LAN1 through MaixCam and TCP232. LAN2 is reserved for computer maintenance, deployment, and teaching.
- Network: the computer, MaixCam, and ESP32 join the controlled LAN during normal operation. Robot-arm LAN1 remains behind MaixCam/TCP232, and LAN2 remains a maintenance path.

See the [overall plan](docs/overall-plan.md), [runtime baseline](docs/runtime/README.md), and [deployment baseline](docs/deployment/README.md).

The primary operator interface is now the [localhost web console](docs/console/control-console-ui.md). It keeps video dominant, provides full chassis and robot-arm debug controls, and calls the existing Python device clients through a loopback-only backend.

Subsystem and operating documentation:

- [Offline runtime integration candidate](docs/integration/offline-runtime-candidate.md)
- [ESP32 MicroPython development](docs/esp32/development.md)
- [Computer-to-ESP32 chassis TCP link](docs/esp32/chassis-tcp.md)
- [Daily development session and troubleshooting](docs/development-session.md)
- [Shared runtime foundation](docs/runtime-foundation.md)
- [Robot-arm YOLO manual control](docs/robot-arm/yolo-manual-control.md)
- [One-dimensional AprilTag rail lock and task interface](docs/console/localization-state-machine.md)
- [Baseline and advanced drawing relocation modes](docs/console/drawing-control-modes.md)
- [Localized Baseline coordinate rehearsal](docs/console/localized-baseline-simulator.md)
- [PC grouped drawing tools](app/README.md)

As of 2026-09-03, the [dated deployment record](docs/deployment/2026-09-03-esp32-maixcam.md)
records the ESP32 v3 service, MaixCam arm/video activation and measured arm
feedback. A subsequent attended drawing test completed four strokes, with
operator confirmation of drawing completeness.
These are bounded L2/L3 results, not coordinated L4, metrology, cold-start or
automatic recovery acceptance. A Git update does not deploy or start hardware.

Use the flat CLI from the repository root for routine connection management:

```powershell
.\robot status
.\robot connect
.\robot details
.\robot disconnect
```

Launch the unified console from the repository root:

```powershell
.\robot-console.cmd
```

It opens `http://127.0.0.1:8080/`, starts with both device sessions disconnected,
and reads only the ignored `config/console.local.json`. The previous PySide6
interface remains a temporary fallback.

`connect` currently starts only a missing MaixCam video service or computer-side relay and reports ESP32 WebREPL as a maintenance check. It does not start the new ESP32 runtime service, deploy code, enter the ESP32 REPL, or reset a device. See [the development-session guide](docs/development-session.md) for maintenance commands and protection rules.

## Development Workflow

Keep changes bounded, review the current worktree, validate in proportion to
risk, and commit only the relevant files. See [the agent and collaborator
rules](AGENTS.md). Per-task plan files and factual logs are not required.

Real motion of one device is L3; coordinated motion across devices is L4. Both
require explicit confirmation from an on-site person who can operate the
physical emergency stop.

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

## Image-to-stroke workflow

[StrokeReview](docs/console/strokereview.md) provides image/SVG processing,
line-art review and normalized stroke JSON export on the computer. Run
`.\stroke-review.cmd -SkipModels` from the repository root for classic mode.
The imported application lives under `apps/strokereview/`; robot execution and
paper-to-arm calibration remain separate from image processing.

`app/run_drawing.py` is the unified PC entry point for image or reviewed JSON
input and explicit Baseline, Localized Baseline, or Advanced strategy selection.
Localized Baseline remains the only production candidate: direct bounded
chassis movement followed by a fresh one-dimensional AprilTag lock and exact
checkpoint resume. Baseline is open-loop and Advanced remains physically
unvalidated; neither is an automatic fallback. Before hardware use, rehearse
the coordinate and window sequence with `app/localized_baseline_sim.py`.

All drawing-site constants now have one authoritative local source:
`config/drawing.local.json`, copied from `config/drawing.example.json`. It owns
image contain-fit margin, the 700 x 200 mm Home-relative canvas, pen/rack and arm
motion values, physical rail datum/travel, AprilTag-derived JSON origin `r0`, rail
scale and required start tolerance, relocation settings, localization thresholds, camera intrinsics and Tag
world corners. `config/console.local.json` contains only device/video endpoints
and manual-console limits; the current trusted-LAN chassis protocol has no
runtime credential.
