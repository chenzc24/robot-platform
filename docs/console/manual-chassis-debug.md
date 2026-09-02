# Hardware Manual Chassis Debug

The console exposes direct ESP32 manual control only when the ignored local
`manual_chassis.enabled` setting is explicitly `true`. The committed template
keeps it `false`.

## Normal operator flow

```text
Connect → Start manual control → hold a direction → release to stop
                                      │
                                      └──────────→ STOP is always available

End manual control → STOP → Disable → Release
```

`Start manual control` performs Acquire and Enable as one asynchronous operator
action. It renews the lease in the background and unlocks the direction controls
only after ESP32 status confirms ownership and enabled state. Repeated clicks are
blocked while this transition is pending.

Holding a direction sends the first bounded velocity immediately and refreshes it
independently of the lease heartbeat. The refresh interval is at most 100 ms and
is always derived to be well inside the configured velocity hold. Releasing the
button stops refresh and immediately queues STOP.

`End manual control` runs STOP, Disable, and Release in order. The raw Acquire,
Enable, Disable, Release, and manual-unlock controls remain under **Advanced
protocol controls** for protocol diagnosis; they are not part of routine manual
operation.

## Minimal runtime protection

The default attended settings are:

```text
lease:              2000 ms
lease heartbeat:     500 ms
velocity refresh:    100 ms maximum
velocity hold:       500 ms
linear range:       10–200 mm/s (starts at 80)
angular range:      10–400 mrad/s (starts at 240)
```

The normal panel keeps only connection, start/end control, the direction pad,
STOP, and the two speed sliders visible. Raw protocol operations and manual
unlock are collapsed under **Advanced**.

The two timeout classes have deliberately different results:

- Velocity hold expiry sends zero speed and leaves the chassis enabled and the
  lease owned. The operator can jog again without repeating session setup.
- Lease expiry, connection loss, malformed transport, or local execution failure
  sends stop and disable. These conditions require recovery or reconnection.

An explicit ESP32 `ERROR` is reported as `REJECTED` and does not disconnect the
session. A transport failure during a state-changing request remains `UNKNOWN`
and disconnects because its terminal outcome cannot be proven.

The desktop application writes sanitized events and faults to the ignored local
file `logs/console/latest-events.log`. Follow it with:

```powershell
Get-Content logs\console\latest-events.log -Wait
```

This surface is for attended L3 debugging. It is not an emergency stop and does
not replace the physical emergency stop or the immediate L3 safety gate.
