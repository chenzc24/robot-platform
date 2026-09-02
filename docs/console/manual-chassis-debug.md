# Hardware Manual Chassis Debug

The console can expose a direct ESP32 manual-debug session only when the
ignored local `manual_chassis.enabled` setting is explicitly `true`. The
committed template leaves it `false`.

The operator flow is: connect, inspect status, acquire, enable, enable the
manual-unlock toggle, then hold a direction control. Releasing the direction
issues stop; Disable and Release end the session. The panel sends no connection,
lease, enable, heartbeat, or velocity merely from opening the application or
selecting Hardware mode. Turning manual unlock off also issues stop.

While unlocked, the panel renews the configured lease and refreshes a bounded
velocity while a direction is held. The default manual limits match the first
L3 deployment: 50 mm/s linear, 100 mrad/s angular, and a 150 ms hold. The
manual lease is 5 s, leaving time to inspect the post-Acquire status and click
Enable; it begins renewing only after the operator unlocks the session. A local
stop is prioritized ahead of queued velocity refreshes; ESP32 independently
stops on hold expiry, lease expiry, disconnect, parse error, or local fault.

The desktop application writes sanitized live event and fault lines to the
ignored local file `logs/console/latest-events.log`. It records timestamps,
targets, command names, lifecycle, result code, and fault codes only. Follow
the file from a PowerShell terminal with:

```powershell
Get-Content logs\console\latest-events.log -Wait
```

This is an attended L3 diagnostic surface, not an emergency stop and not an
L4 coordinated-control surface. Each real use still requires the immediate
physical L3 safety gate.
