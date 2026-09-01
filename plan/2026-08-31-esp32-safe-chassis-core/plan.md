# ESP32 Safe Free Entry and Cable Status Machine

- Status:`completed`
- Responsible: Agent Implementation
- Highest validation level:`L1`

## Objective

Proceeding from historical audit findings, `src/esp32/app/` Create Default `SAFE_IDLE` Application access and non-hardware-dependent chassis safety machines. Validity fixes the four software problems of "unknown mode automobilization" initial parking that has been clogged over "defunct" and "re-enabled zero" software, with proof of a fake MotorBus regression test. This goal does not migrate to CAN.

## Initial state of the workspace

```text
## main...origin/main
```

The area is clean, the previous L3 PS2 route test has been completed and submitted....The device continues to use the existing historical program, and this goal is to modify only the local official source code.

## Modifyable File

- `.vscode/tasks.json`
- `src/esp32/app/main.py`
- `src/esp32/app/device_config.example.py`
- `src/esp32/app/chassis_control.py`
- `tests/esp32/`
- `docs/esp32/chassis-safety.md`
- `docs/esp32/legacy-chassis-audit.md`
- `docs/esp32/development.md`
- `src/esp32/README.md`
- `plan/2026-08-31-esp32-safe-chassis-core/plan.md`
- `plan/log.md`

## Read-only files and directories

- `src/esp32/legacy/`
- `src/esp32/app/boot.py`, `network_boot.py`, `secrets.example.py`
- ESP32 Device and file systems
- Source information, backup of device and other subsystems

## Shared Dependencies

- History `MotorBus` Expected interface:`prepare_speed_mode`, `set_acc`, `set_speed`, `stop_all`, `disable_all`.
- Baseline of C1/C2 blockages and speed limits in audits
- The current MicroPython compatibility target; official modules cannot rely on the CPython feature.

## Design boundaries

- `SAFE_IDLE` It's the only retreat that is missing, unknown or not yet moving, without initializing any motor hardware.
- The chassis state at least includes `DISABLED`, `ENABLING`, `ENABLED_STOPPED`, `MOVING`, `FAULT`.
- Rejecting non-zero movement targets in case of failure;`stop()` Send zero targets to the bus every time, without relying on software caches.
- Enabling sequence must send zero targets before and after driver initialization; any abnormal entry `FAULT` And try to stop the car, it's dead.
- This target only provides security core and false bus tests, and does not claim that real drive feedback or hardware actions have been validated.

## Expected work

1. Yes `main.py` Add visible run mode to integration, unknown mode back `SAFE_IDLE`.
2. Accomplish the chassis, speed limit, enable/stop/facility and failure back.
3. Use Standard Library `unittest` And fake MotorBus overwhelm block and error path.
4. Add VS Code test assignments and secure core files.
5. Update historical audit status without changing the freeze.

## Validation

- `python -m unittest discover -s tests/esp32 -p "test_*.py"`
- `python -m compileall -q src/esp32/app tests/esp32`
- Fake MotoBus call sequence and status.
- Unknown mode of running to `SAFE_IDLE`.
- Secret scan, VS Code JSON analysis.
- `git diff --check`
- `git status --short --branch`

## Actual results

- Formal `main.py` Only allowed `safe_idle`;configuring missing, nonstring, history `ps2`/`idle` , or any other unknown value is converted to `SAFE_IDLE`, and do not import sports hardware.
- `device_config.example.py` Explicitly `RUN_MODE` Default set to `safe_idle`.
- New hardware is irrelevant `SafeMecanumChassis`, Achieved `DISABLED`, `ENABLING`, `ENABLED_STOPPED`, `MOVING`, `FAULT` Five.
- (a) Enable the energy process to be performed by "total failure - write zero - drive initialization - write zero again";`stop()` Zero for each bus;`disable()` Write zero and fail.
- Momentology retains historical line speed, angular speed, wheel speed and acceleration caps, and rejects NAN, infinity and non-positive acceleration before the bus is written.
- An abnormal entry of power, motion or failure bus `FAULT`; the energy and exercise anomalies will stop as much as possible, and the malfunctions will remain in the upper layers.
- New 12 Standard Library `unittest` The fake MotorBus test, covering C1/C2 blockages, normal state conversion, limit band, zero speed, duplicate energy, non-limited input and three types of failure path, all passed.
- Add a new VS Code security test task and independent design document; history snapshot unmodified and recorded in the audit document as "local return protected, not hardware verified".
- VS Code JSON, Python Static Compiled, Secret Scan and Git Format Check passed.
- This round is not connected, write or drive ESP 32, CAN or electric.

## Outstanding matters

- The real MotorBus/CAN adapter has not yet been migrated, the status only means calling unattended anomalies, not driving confirmed execution.
- PS2 reception, lost parking, control, Camera UART, network control, sensors, tracks and rudders are not moving.
- The official security core has not yet been implemented at MicroPython, nor has L2/L3 verification or deployment taken place.

## Experience signal (for manual review)

- The core of the implementer's security can be placed in a fixed order of call by relying on injection and false bus, illegal state and failure rollback, and then access real-driven feedback.

## Intent to submit

```text
feat: add ESP32 safe chassis state machine
```
