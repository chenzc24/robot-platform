# Guarded ESP32 Chassis L3 Runbook

## Purpose

This runbook defines the first single-device chassis L3 procedure. It is not a
normal operating mode and it does not validate a coordinated arm or vision
task.

The L3 composition is direct:

```text
computer -> authenticated RCP/TCP v2 -> ESP32 -> CAN -> four motor controllers
```

It uses the preserved legacy CAN facts: controller `0`, `1 Mbps`, TX `8`, and
RX `18`. `CAN.send()` is only local transmit acceptance, not motor feedback.

## Hard boundaries

- `tcp_v2_l2` remains the normal deployed, no-motion mode.
- `tcp_v2_l3` creates the CAN peripheral and immediately attempts zero-speed
  plus disable output for every motor.
- `L3_MOTION_PERMITTED` defaults to `False`. While false, the listener can
  report state but rejects `ENABLE` and `VELOCITY`.
- The first allowed L3 tool is fixed at forward `50 mm/s` for `200 ms`. The
  service separately limits linear speed to `50 mm/s`, angular speed to
  `100 mrad/s`, and hold duration to `200 ms`.
- Loss of the TCP connection, lease timeout, velocity-hold timeout, malformed
  input, CAN error, or local service fault attempts stop plus disable.

## Required sequence

1. Complete local tests and inspect the exact release files.
2. Back up the working L2 device files and preserve USB recovery access.
3. Deploy the L3 runtime with `L3_MOTION_PERMITTED = False`.
4. Restart the ESP32 and confirm authenticated `STATUS` reports a disabled
   chassis. If CAN-safe-output fails, stop and restore L2; do not attempt
   motion.
5. Immediately before changing the local L3 flag to `True`, obtain a fresh
   on-site confirmation: emergency-stop operator, raised/restrained chassis or
   clear test zone, clear cables and people, arm disabled/safe, and agreement
   on the 50 mm/s for 200 ms wheel-rotation test.
6. Run the explicit test client with both `--execute` and
   `--safety-confirmed`. It authenticates, acquires a 5 s lease to cover the
   four-motor initialization sequence, enables, renews to a 1 s motion lease,
   sends one bounded velocity, waits for the 200 ms hold expiry, verifies the
   disabled state, and releases control.
7. If any wheel behavior is unexpected, use the physical emergency stop first.
   Do not retry motion automatically. Restore L2 after a CAN or controller
   fault.

## Execution command

Set the credential only in the local environment, then substitute the current
ESP32 endpoint:

```powershell
python tools/esp32/l3_chassis_test.py --host <esp32-address> --execute --safety-confirmed
```

Without `--execute`, the tool is a dry run. It has no speed, duration, or
direction override so the reviewed first-test limits cannot be widened from the
command line.
