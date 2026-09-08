# ESP32 one-dimensional line-following core

`src/esp32/app/line_following.py` is a transport-neutral control layer between
digital line sensors and `SafeMecanumChassis`. It is intentionally not a
complete runtime mode: it does not initialize GPIO, create a loop, acquire a
TCP session, enable motors, or deploy itself.

## Boundary

The high-level rail coordinate remains one-dimensional, but a freely rolling
chassis may need yaw correction while progressing along that axis:

```text
line_left + line_right ──→ vx along rail + bounded omega correction
station_left + station_right ──→ immediate stop + debounce ──→ station
```

`vy` is always zero. The controller accepts a `direction` of `1` or `-1` for
the progress direction. Sensor-to-yaw mapping is a separately configured
`steering_sign`; reverse travel must be physically validated because usable
sensor placement depends on the chassis geometry.

Four raw integer readings are required from the injected callable:

```python
{
    "line_left": 0,
    "line_right": 1,
    "station_left": 0,
    "station_right": 0,
}
```

The electrical `active_level` must be explicitly set to `0` or `1`, and
`center_pattern` must be either `both_active` or `both_inactive`. This separates
electrical polarity from whether the two probes sit on the line or straddle it
when centered. Neither value is inherited from the legacy example because its
comments and decisions conflict. The station pair is intended for a transverse
mark or equivalent local station signal; AprilTag remains the stopped, PC-side
precision lock.

## Lifecycle interface

```python
config = LineFollowConfig(
    active_level=0,
    steering_sign=1,
    center_pattern="both_active",
)
follower = LineFollower(chassis, read_four_sensors, config)

follower.start(direction=1)  # verifies enabled_stopped and writes stop
while follower.status_snapshot()["state"] == "following":
    follower.step()
follower.stop("task_cancelled")
```

The production scheduler should call `step()` faster than `max_step_gap_ms` and
continue polling the existing TCP connection-health safety path. This module
contains no blocking sleep. Its states are:

- `idle`: no line-following command owner;
- `following`: accepting fresh local sensor samples;
- `station`: station pair remained active for `station_confirm_ms` while the
  chassis was stopped;
- `fault`: sensor input, step timing, chassis state, or command execution failed.

Both line sensors inactive causes an immediate stop. It becomes a latched local
fault after `line_loss_timeout_ms`; reacquisition before that deadline may
resume. A station candidate also stops immediately and resumes only if the mark
disappears before confirmation.

The layer calls `stop()` but never disables motors. Connection loss and CAN
errors remain governed by the existing chassis runtime; the future task owner
must decide when a local line-following fault also requires `disable()`.

## Intended coordinated sequence

```text
arm safe pose confirmed
→ ESP32 line-follow start/step
→ station confirmed and chassis stopped
→ physical settling interval
→ PC AprilTag rail lock
→ scalar JSON offset
→ arm task may begin
```

No RCP/TCP command starts this sequence yet. Adding one changes the shared
protocol and requires coordinated ESP32, PC client, simulator, console, and
documentation work.

## Validation boundary

L1 fake-chassis tests cover polarity conversion, forward and reverse command
signs, correction mapping, immediate line-loss stop, station debounce, scheduler
timeout, invalid input, drive failure, and explicit lifecycle transitions.

They do not validate GPIO assignments, voltage levels, sensor placement, black
or white line behavior, reverse-travel geometry, traction, tuning, CAN execution,
physical stop distance, obstacle detection, or coordinated L4 interlocks. Those
require a separate configuration/deployment goal followed by an attended,
low-speed L3 test.
