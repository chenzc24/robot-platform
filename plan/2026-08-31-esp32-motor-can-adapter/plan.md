# ESP32 MotorBus and CAN frame adapter migration

- Status:`completed`
- Responsible: Agent Implementation
- Highest validation level:`L1`

## Objective

Selective displacement of motors from the freeze of historical snapshots to the CAN speed model protocol, which forms a formal injection into the safety chassis. `MotorBus`Using fake CAN to verify 29-bit extension ID, 8-bit load, small-end parameter coding, speed limit, enabling zero-point energy, four power mass failure to continue and abnormally roll back. This target does not construct MicroPython real CAN, does not connect or deploy ESP32.

## Initial state of the workspace

```text
## main...origin/main
```

Workspace clean. Formal chassis safety machines and 12 fake MotorBus tests have been submitted; Real device is still running the historical PS2 program.

## Modifyable File

- `src/esp32/app/motor_bus.py`
- `tests/esp32/test_motor_bus.py`
- `docs/esp32/motor-can.md`
- `docs/esp32/chassis-safety.md`
- `docs/esp32/development.md`
- `docs/esp32/legacy-chassis-audit.md`
- `src/esp32/README.md`
- `plan/2026-08-31-esp32-motor-can-adapter/plan.md`
- `plan/log.md`

## Read-only files and directories

- `src/esp32/legacy/`
- Other `src/esp32/app/` Documentation
- `.vscode/tasks.json` And established tests.
- ESP32 Device, File System, Source and Device Backup

## Shared Dependencies

- `SafeMecanumChassis` Five interfaces for MotorBus.
- History CAN protocol: 29-bit extension ID, host ID `0xFD`, speed mode parameter index and small end load.
- Hard maximum 44 Rad/s and default PI/filtration values for historical drive speed.
- The current L1 results do not prove that Can has been sent or sent, driven ACK or real power.

## Design boundaries

- CAN objects are injected through construction parameters; official modules are not imported or constructed directly `esp32.CAN`.
- All frames must strictly verify the electrical ID, the type of communication, the parameter index and the 8 byte load.
- Zero speed before and after the initialization of the single power.
- Bulk parking/deactivation continues to try the rest of the power, even if one frame fails, and then throws the first anomaly again.
- Once the batch initialization fails, try to stop and disable the entire target.
- `CAN.send()` Back `False` Considers the dispatch failed;`None` Compatible with other normal return values for current MicroPython API.
- Do not interpret "the frame sent" as "drive executed"; AK and status feedback left for subsequent agreement.

## Expected work

1. Completing CAN Extension ID, Parameter Load and MotoBus Base Command.
2. Initialize safe single/multi-power speed patterns, stop and disable.
3. Use a fake CAN cover frame vector, limit band, call order, send failure and batch rollback.
4. Add the MotoBus-SafeMecanumChasis integration test.
5. Update design, develop, audit and source access documents.

## Validation

- `python -m unittest discover -s tests/esp32 -p "test_*.py"`
- `python -m compileall -q src/esp32/app tests/esp32`
- Fixed CAN frame test vector and small-end float/integer assertion.
- The rest of the machine tried and rolled back after the fake CAN failed.
- Secret scan.`git diff --check`, `git status --short --branch`.

## Actual results

- Add an official that can be injected into the CAN object `MotorBus`, achieve a strict 29-bit extension ID, fix an 8-byte load, uint32/float32 small-end parameter written, limited validation and ±44 Rad/s drive side limit.
- Initialization of single generators at zero velocity before and after performance; Batch parking and failure to process the remaining generators after failure of the single frame; Endeavour to stop and disable the complete target group when initialization fails.
- Add 10 new FakeCAN tests, running in conjunction with the existing core of 12 chassis security tests; all 22 through ... source code and test static compilation.
- Add a new CAN adaptor design document and synchronize the update of chassis security, development portal, history audit and source access description.
- Complete secret, variance format and submission range check; no connection, write or drive any real hardware.

## Outstanding matters

- The historical parameter index has not been confirmed with official drive information, default PI/filtration values and feedback frames.
- The real MicroPython CAN, CAN-led foot, 1 Mbpsport rate, sent back semantics and fus-off is not verified.
- There is no AK, drive state, failure code, actual speed or real rollback results; "send successful" cannot be interpreted as "drive executed".
- The next goal should be to complete the protocol data check and then design the L2 CAN connection check that does not connect the power plant; any real enabler or movement must still establish the L3 target and re-enter the manual security door.

## Experience signal

- Can send frame consistency and driver validation must be used as two separate validation layers; FakeCAN can only close the former, not substitute for ACK and state feedback.

## Intent to submit

```text
feat: add tested ESP32 motor CAN adapter
```
