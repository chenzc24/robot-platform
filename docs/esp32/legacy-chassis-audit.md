# ESP32 Existing chassis source baseline and static audit

- Baseline source: ESP32 filesystem backup root directory
- Backup time identification:`20260831-111429`
- Version snapshot:`src/esp32/legacy/chassis_2026_08_31/`
- Audit Level: L1, static translation only and no hardware simulation
- Deployment findings: **History snapshot prohibits direct deployment or integration `src/esp32/app/`**

Follow-up status:`src/esp32/app/` Default achieved in stand-alone goal `SAFE_IDLE` And the fake MotorBus status machine, which established back-up protection for C1/C2; Freezing snapshots remained the same. The security core has not yet accessed CAN or deployed the real machine, and C1/C2 cannot be marked as hardware validation. [`chassis-safety.md`](chassis-safety.md).

## 1. Scanning integrity

The backup root directory of the device contains the same 11 Python files as the versioned snapshot, the size of which corresponds to each item of SHA-256. The files are valid UTF-8, but the LF and CRLF are used in combination and the original trail blank is maintained;`.gitattributes` The freeze snapshot closes text conversion and blank specifications check to keep the byte level as it is. The exemption does not apply to the current source code.

| Documentation | Bytes | SHA-256 |
|---|---:|---|
| `boot.py` | 217 | `f3a6a0a4ad763ab19eee1a70a9edab10b61a1f5515ef9dd39f791d7c97c85673` |
| `chassis_control.py` | 6936 | `9485118ca20ba76889b6daf7255380835a0726fb26b825c10d5835f4c149865a` |
| `hcsr04.py` | 4025 | `32c2a48d4d24d696d1cb388a108766af767843d416daac5984bb8125a455ec2c` |
| `main.py` | 7434 | `620bafd49776e4ef4fb003838db2c4f10db44869f8fe351a891e5dc66f52dc7b` |
| `motor_lib.py` | 4385 | `605baaa24b368f1d96a7066b88f2b04fc6c74011d87d5cdef6ad77033ee80e51` |
| `ps2_control.py` | 7931 | `11e32f328557838a05eb7d81c6ba89129aab8ed1d6222e7350c9276062b99ee8` |
| `ps2_lib.py` | 8595 | `a2eb5fd6a8751d77e8d1ec6ccb39d9f749efe9c7a98d471d6faea5dc8b6f0972` |
| `robot_config.py` | 2340 | `df93503943b2a85b62fe2caef63b06dd6873ca538ab2105f60a510ee1b93717e` |
| `sensor.py` | 3347 | `3bcd6324ce7c717e91d93c84c487345742aee5379e8df02201109e4b19ddee41` |
| `servo_control.py` | 4842 | `6dca54b74916dfc54d3d37d30878210f8e1684a90bd53476fafba8cf6bc95bb9` |
| `servo_lib.py` | 12790 | `fbb1f88e1e6d4ce1bf3973f4c819eaab98c59977ea26870987d4674463f1a537` |

Root directory and device `SmartHybridChasisDemo/` The same 11 pairs of files have been identified in the backup target, so this is only a one-in-one directory, not a second one.

## 2. Current structure

```text
main.py
Ideas - Top Level Initialization Camera UART, CAN, chassis objects and receiver lines Cheng
├── RUN_MODE == "ps2" → PS2Receiver → ps2_loop()
└ - Any other RUN MODE auto-example chassis and rudder manoeuvres

ps2_loop()
Idea-- normal swing control.
Idea-- Stop, disable and re-enactment keys.
Ideas — Carmela UART raw string
└ - PS2 L1 key into the internal loop of the barrier
```

## 3. Must be repaired prior to deployment

### C1: Unknown running mode moves automatically

`robot_config.py:25` Only `"ps2"` Visible;`main.py:137-230` Execute any other value forward, backward, transverse, rotate, wheel speed and optional rudder test. The configuration is missing, spelling errors or future growth patterns fall into the example of movement, not free time.

Request: Run mode uses a visible white list; unknown, missing resolution failed to enter `SAFE_IDLE`, prohibition of initialization or enabling motion implementers. Demonstrations can only be activated by independent L3 test portal and manual confirmation.

### C2: Disable states can still be written as non-zero targets, re-enacting unenforceable zero before the energy becomes available

`chassis_control.py:87-92` Re-initiation of the energy call drive, but no visible dispatch of zero speed; and `_motors_stopped` Make it real.`stop()` Return directly when the sign is true.`drive()` and `drive_wheel_speeds()` Do Not Check `motors_enabled`, so when you fail, you write non-zero targets to the drive. No hardware simulation confirms that the call sequence actually produces speed writing.

If the drive saves the target value during a failure, then the re-enactment may immediately execute the old target ... Whether to save requires access to the drive protocol and confirmation of L2/L3, but the software does not currently create a secure boundary.

Require: Reject all non-zero targets in case of failure; Before enabling, enabling and confirming zero targets; Stop relying on software caches; Status machines at least distinguish `DISABLED`, `ENABLING`, `ENABLED_STOPPED`, `MOVING` and `FAULT`.

## 4. High-risk issues

### H1: Import module i.e. initialised real hardware

`main.py:57-118` Creates Camera UART and CAN outside the function, emptys CAN receiving queues, creates chassis objects, selects the initialization wheel and starts the thread.`ps2_control.py:128-129` Read time and configure retrospects and ultrasounds when importing. Importing modules alone changes the state of hardware, does not allow security testing, diagnoses or starts in the order of dependence.

Requirements: all hardware construction and linear startup move into a visible life cycle; first configuration check and security set up, then start the service one by one.

### H2: Can failure to initialize may result in an infinite repetition cycle

`main.py:65-76` Wait for one second after the initialization anomaly of any CAN capture `machine.reset()`, there is no maximum test, failure or maintenance of the entrance... permanent connection, lead or resource conflict will result in continuous repositioning and repeated execution `boot.py` Network initialization.

Request: Record specific anomalies and enter maintenanceable `FAULT`Maintaining power failure; only those errors that are clearly recoverable can be retried.

### H3: We've got a back-up mode. The door.

`ps2_control.py:50-105` Once you're inside the infinite cycle, read it. `fresh`, but without checking the value. The exit key cannot be reliably identified when the handle is missing; the previously released motor target may continue. The ultrasound is only `0 < distance < 20` Time parking, time out, abnormal and invalid distance is not a failure to stop. There's a 0.5-second blockage in the cycle, 250 millisecond fresh window beyond the normal PS2 path.

(b) Control ownership, handle/mission heartbeat, sensor freshness and validity, any failure to stop immediately and exit or fail.

### H4: No driver feedback and verified status

`motor_lib.py` Only send CAN write commands, no ACK, status read, rollback after failure to report or partial initialization. Four machines are configured and controlled in sequence, and the intermediate abnormality may leave a mixed state. `motors_enabled` and `_motors_stopped` It's just a local assumption.

Requires: Introduction of driver status queries and command results; Bulk failure to stop and disable all generators; Console status shall not be "sent" as "executed".

Follow-up status: Formal `MotorBus` Strict frame verification has been achieved through false CANs, batch failure continues and group rolls back, but no driver ACK or status read yet, so H4 only completes software side protection, not closed. [`motor-can.md`](motor-can.md).

### H5: Retain the rudder to generate action during start-up.

Current `RESERVE_SERVO_ENABLED=False`, so it's not implemented.`main.py:85-99` It's going in. `main()` Reset the number of circles, lock and move to the initial angle. And `servo_lib.py:52-55` Use two arguments `time.ticks_add()`; MicroPython 1.27.0 of the current round connected had an error in the number of parameters returned in this form, compatibility not resolved.

Request: The rudder initialization should not be at the import stage; The time compatibility layer must be tested for the current firmware; Any return zero, locking or initial angle movement is handled by L3.

## Medium risk and maintenance issues

- `ps2_loop()` The normal path has a 250 ms snapshot of freshness, parking keys and power failure keys, which are the safe foundation to keep; but the thread stops only changing the sign, and does not wait for the back-stage line to exit.
- Carmela UART receives a shared dictionary cross-line to pass a nudist string. Any data received immediately `ok`, no message boundary, length constraint, serial number, CRC, timeout or response matching; currently only print data, and no action has been executed.
- Camera receiving threads only. `UnicodeError`, but decoded `errors="replace"`, this anomaly usually does not happen; other UART and thread error will directly terminate the reception.
- `sensor.py` and `ps2_control.py` Repeats the recoding code and the hard coding lead, creating two realization sources; the official code should retain a sensor service.
- Positive protection exists in the velocity layer: the body line speed limit is 0.60 m/s, the angle speed limit is 0.80 rad/s, the wheel speed is standardized at 200 RPM, and the motor drive is capped at 44 rad/s. The limit is not a substitute for the performance state, the heartbeat and feedback.
- `main.py`, `hcsr04.py` and `sensor.py` Both contain examples of real hardware that can run directly, and then move to a clear L3 test directory.

## 6. L1 validation results

- 11 documents through CPython `compileall`, certify only the source code, does not import or execute MicroPython hardware module.
- Use a fake MotorBus to perform a purely chassis logical check: Superbody commands will be limited to the configuration speed limit.
- Same simulation confirmed: New underboard object `stop()` no bus parking command; call after failure `drive()` There are still four non-zero speed writing operations. It's proof of certainty in C2.
- No ESP32 connection, no upload file, no Can/UART message, no real exercise.

## 7. Follow-up rebuilding of borders

The next target should be moved from historical snapshots to a selective one. `src/esp32/app/`, instead of copying:

1. Create safe application access and visible mode, default `SAFE_IDLE`.
2. Reconstruct the electrical/disk status machine, first repair C2 and add a false bus regression test.
3. Move PS2 normal control to a control source, maintain 250 milliseconds of unconnected parking; retrace not moving into the running path.
4. Change Camera UART to a protocol adapter with a boundary, serial number and verification, and the current raw string is kept only as a historical record.
5. Separating sensors and rudder services, the initialization of all motion generation is delayed until control and safety confirmation is obtained.
6. Once the L1 simulation and protocol tests have been completed, establish an independent L2 deployment target;
