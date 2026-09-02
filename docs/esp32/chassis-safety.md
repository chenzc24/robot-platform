# ESP32 Chassis Safety Core

- Implementation: `src/esp32/app/main.py`, `application.py`, `chassis_control.py`, `chassis_motion_tcp_service.py`
- Current validation: L1 with a fake MotorBus; no real CAN or motors
- Deployment status: not deployed; the device still runs the historical program

## 1. Safe Default Entry

Production `main.py` currently supports only `safe_idle`:

```text
missing configuration ─┐
unknown run mode ──────┼→ SAFE_IDLE → no CAN, motors, UART, or servo initialization
ps2 / idle ────────────┘  rejected until those modes are migrated and validated
```

Add a run mode to `SUPPORTED_RUN_MODES` only after its full behavior and safety gates are implemented. The legacy fall-through path that runs motion examples for any mode other than `ps2` is intentionally excluded.

## 2. Chassis State Machine

```text
DISABLED
   │ enable_motors()
   ▼
ENABLING ── any failure ──→ FAULT
   │
   ▼
ENABLED_STOPPED ←── stop()/zero velocity ── MOVING
   │                                          ▲
   └──────────── valid nonzero drive ─────────┘

any normal state ── disable() ──→ DISABLED
any bus failure ── attempt stop + disable ──→ FAULT
```

Rules:

- Only `DISABLED` may begin enable.
- Enabling prepares speed mode and writes zero before motion is allowed.
- Only `ENABLED_STOPPED` and `MOVING` accept drive commands.
- `DISABLED`, `ENABLING`, and `FAULT` reject motion without writing speed.
- `stop()` always calls `stop_all()` and never skips a stop because of cached state.
- `disable()` writes zero and disables every motor.
- A bus exception attempts `stop_all()` and `disable_all()`, records the error, and retains `FAULT`.

## 3. Input Limits

- Maximum linear speed: 0.60 m/s.
- Maximum angular speed: 0.80 rad/s.
- Maximum absolute wheel target: 200 RPM.
- Reject NaN and positive/negative infinity before any bus write.
- A near-zero four-wheel target calls `stop_all()` explicitly.

These values were inherited from legacy code. Their presence proves a software limit exists; it does not prove that the limits are safe for the real chassis.

## 4. MotorBus Contract

```text
prepare_speed_mode(motor_ids)
set_acc(motor_id, acc_rad_s2)
set_speed(motor_id, speed_rad_s)
stop_all(motor_ids)
disable_all(motor_ids)
```

The production `MotorBus` has passed fake-CAN tests for frames, explicit zero writes, batch-failure continuation, and initialization rollback. It has no ACK or driver feedback, so a successful send cannot be reported as confirmed motor execution. See [Motor CAN](motor-can.md).

`SafeMecanumChassis.status_snapshot()` exposes state, four wheel targets, and the last error. `MotorBus.status_snapshot()` exposes sent-frame count, send failure, and the explicit absence of ACK support.

RCP/TCP v3 treats the authenticated TCP connection as the single controller.
Its local health deadline stops and disables the chassis if the connection stops
producing valid requests; there is no acquire/release lease object.

## 5. Local Validation

Run `ESP32: Run safety tests` in VS Code or:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests\esp32 -p "test_*.py" -v
```

Coverage includes safe-idle fallback, stop from disabled, drive rejection while disabled, zero-before-enable ordering, active-state transitions, four-wheel limiting, explicit zero-speed stop, post-disable rejection, fault rollback, non-finite input rejection, structured status, CAN send counts, authenticated-session behavior, and connection-health timeout.

## 6. Not Yet Covered

- MicroPython CAN, real CAN, and motor-driver feedback.
- PS2 input and multi-client control arbitration.
- Sensors, homing, servos, and measured motor feedback.
- Real motor enable/disable, stop, fault, and link-loss behavior.

L1 results do not replace L2 connectivity validation or the L3 motion safety gate.
