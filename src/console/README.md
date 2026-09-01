# Computer Runtime Source

`chassis_tcp_client.py` and `chassis_tcp_probe.py` implement the first non-motion computer-to-ESP32 runtime proof. They use RCP1/TCP on the configured LAN port and do not use WebREPL.

The current allowlist is only `HELLO`, `PING`, and `STATUS`. No motion command exists, and the client does not retry automatically. Run the probe only while the matching bounded ESP32 probe is active:

```powershell
python src/console/chassis_tcp_probe.py --host <current-esp32-ip>
```

Motion control, authentication, control leasing, heartbeat stop, reconnect policy, and console integration require a separate safety goal.
