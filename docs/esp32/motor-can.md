# ESP32 Electric Can Fitr

- Achieved:`src/esp32/app/motor_bus.py`
- Test:`tests/esp32/test_motor_bus.py`
- Current level: L1 fake CAN
- Deployment status: Not deployed, not connected to real CAN

## 1. Migration borders

Formal `MotorBus` From History `motor_lib.py` Selective migration of 29-bit extension ID, parameter writing and speed mode commands. It receives CAN objects by construction parameters, does not directly import or create `esp32.CAN`, so you can verify the protocol and the path to failure.

```text
SafeMecanumChassis
        Five MotorBus interfaces
        ▼
     MotorBus
        │ 29 validated extension frames
        ▼
  Injecting Can Object (currently FakeCan)
```

History snapshots remain unchanged, formalizing the non-reuse of the "quiet load" and "first error to stop bulk processing immediately".

## 2. Extension ID and payload

29-bit extension ID:

```text
bit 28.24:comm  type (5)
bit 23.8: data2/ hostID (16 bit, 0x00FD for parameter command)
bit 7.0: motor id (8 bit)
```

Fixed test vector:

```text
comm_type=0x12, data2=0x00FD, motor_id=1
→ extended_id=0x1200FD01
```

Parameters written to load fixed to 8 bytes, small end:

```text
byte 0.1: argument indexuint16
Byte 2.3: Reservations 0
byte 4.7: uint32 or float32 parameter values
```

Example speed mode frame:

```text
ID      = 0x1200FD01
Payload = 05 70 00 00 02 00 00 00
```

The adaptor rejects error length, cross-border ID, cross-border byte, NN and infinity, and does not automatically cut or fill the wrong load.

## 3. Orders and parameters

| Functions | Type of communication/parameters | Current constraints |
|---|---|---|
| Energy | `comm_type=0x03` | 8 byte zero load |
| Incompetence | `comm_type=0x04` | 8 byte zero load |
| It's not working. | `comm_type=0x04` | First bytes 1, remaining 0 |
| Speed Mode | `0x7005=2` | uint32 small end |
| Speed Target | `0x700A` | float32, limit ±44 Rad/s |
| Speed PI | `0x701F/0x7020` | Non-negative limit |
| Speed Filter | `0x7021` | 0..1 |
| Speed up. | `0x7022` | Positive limit |

These indexes, the default PI and filter values inherit history, have not yet been re-confirmed with official driver documents or real status.

## 4. Order of safe calls

Initialization of single power speed mode:

```text
Incapacitation, failure, speed mode, PI, filter, speed.
Zero speed, zero speed, zero speed.
```

Batch rules:

- `stop_all()` Even if a power failed, it continued to write zero to the remaining one, and finally dropped the first anomaly.
- `disable_all()` Even if the parking phase fails, try to lose all the power.
- `prepare_speed_mode()` After the initialization of any of the engines failed, try to stop and disable the entire target, and then throw back the anomaly.
- `CAN.send()` Clear Return `False` is considered a failure;`None` Accepted to fit current MicroPython API.

## 5. L1 test

Add 10 new false CAN tests totalling 22 tests with the chassis core:

- 29-bit extension ID fixed vector.
- Speed mode unit 32 load fixed vector.
- Float32 small end code and 44 Rad/s driver limit.
- ID, payload, non-limited speed and `CAN.send=False` Reject.
- The single power gives a zero-speed sequence.
- `stop_all()` Continue with the other generators after the single frame fails.
- `disable_all()` We lost all the power.
- Full rollback after batch initialization failed.
- Official MotoBus `SafeMecanumChassis` After integration. `ENABLED_STOPPED`The last four frames are zero speed.

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests\esp32 -p "test_*.py" -v
```

## 6. Unsolved

- Real `esp32.CAN` Construct, quote, 1 Mbpsport rate and send back semantics.
- Driver AK, state, failure code, physical speed and enabling status read.
- Can bus shut down, bus-off, arbitration failure and reconnection strategy.
- The real rollback of the four power units.
- Real power, parking and incompetence.

Therefore, the current state only indicates that frame coding and software call sequences are correct, not that the power is being successfully implemented. Next steps should be to confirm the protocol and feedback frame with the manufacturer's information, and then design not to connect the L2 CAN to the power generator;
