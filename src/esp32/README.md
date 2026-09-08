# ESP32 MicroPython Source

This directory is the version-controlled source of truth for ESP32 software. The root-level `ESP32/` directory is an ignored, read-only resource archive and must not be modified from here.

## Current Status

`app/` contains the Wi-Fi/WebREPL bootstrap, default `SAFE_IDLE` entry point,
structured runtime status, the chassis safety state machine, injectable CAN
MotorBus, and a one-client RCP/TCP v3 listener. `tcp_v3_l2` composes
`NoMotionChassis` and rejects motion without constructing CAN. `tcp_v3_l3`
composes the reviewed CAN runtime when local motion permission is enabled. The
authenticated TCP connection is the control session; no acquire/release lease
exists. The CAN path still reports commanded state rather than measured driver
feedback.

The existing device program is preserved byte-for-byte under `legacy/chassis_2026_08_31/`. It is a historical snapshot, not a deployment source. See the [legacy audit](../../docs/esp32/legacy-chassis-audit.md), [chassis safety core](../../docs/esp32/chassis-safety.md), [computer-ESP32 TCP link](../../docs/esp32/chassis-tcp.md), [MotorBus design](../../docs/esp32/motor-can.md), and [runtime foundation](../../docs/runtime-foundation.md).

`chassis_tcp_service.py` and `chassis_tcp_probe.py` provide an isolated non-motion RCP1/TCP proof. They are not yet a resident startup service and deliberately do not connect to CAN or the safety state machine.

`line_following.py` provides an injected, non-blocking line-following control
core for a one-dimensional rail. It is not wired into a runtime mode or TCP
command yet; see the [line-following boundary](../../docs/esp32/line-following.md).

Run the local source check from VS Code (`ESP32: Check Python sources`) or PowerShell:

```powershell
.\.venv\Scripts\python.exe tools\dev\check_python.py src/esp32/app
```

USB and WebREPL procedures are documented in [ESP32 Development](../../docs/esp32/development.md).
