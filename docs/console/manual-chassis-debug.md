# Hardware Manual Chassis Debug

The console exposes direct ESP32 manual control only when the ignored local
`manual_chassis.enabled` setting is explicitly `true`. The committed template
keeps it `false`.

## Normal operator flow

```text
Connect → Enable → hold a direction → release to stop
               │
               └──────────→ STOP is always available

Finish motion → STOP → Disable → Disconnect
```

The successful authenticated TCP connection is the control session. There is no
separate acquire, release, manual-unlock, or operator lease. `Enable` is available
after the ESP32 reports an authenticated connection and motion permission.

Holding a direction sends the first bounded velocity immediately and refreshes it.
The refresh interval is at most 100 ms and
is always derived to be well inside the configured velocity hold. Releasing the
button stops refresh and immediately queues STOP.

`STOP` zeros the requested velocity and leaves the motors enabled for the next
jog. `Disable` stops and disables the chassis but keeps the authenticated TCP
connection available, so the operator can use `Enable` again. `Disconnect`
ends the session; reconnecting requires only `HELLO` authentication and `Enable`.

## Minimal runtime protection

The default attended settings are:

```text
connection health:  2000 ms
health ping:          500 ms
velocity refresh:    100 ms maximum
velocity hold:       500 ms
linear range:       10–600 mm/s (starts at 80)
angular range:      10–800 mrad/s (starts at 240)
```

The normal panel keeps only Connect/Disconnect, Enable/Disable, the direction
pad, STOP, and the two speed sliders visible.

The two timeout classes have deliberately different results:

- Velocity hold expiry sends zero speed and leaves the authenticated chassis
  enabled. The operator can jog again without repeating session setup.
- Connection-health timeout, connection loss, malformed transport, or local
  execution failure sends stop and disable and closes the session.

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
