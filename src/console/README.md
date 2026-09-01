# Computer Runtime Source

`chassis_tcp_client.py` and `chassis_tcp_probe.py` implement the first non-motion computer-to-ESP32 runtime proof. They use RCP1/TCP on the configured LAN port and do not use WebREPL.

The current allowlist is only `HELLO`, `PING`, and `STATUS`. No motion command exists, and the client does not retry automatically. Run the probe only while the matching bounded ESP32 probe is active:

```powershell
python src/console/chassis_tcp_probe.py --host <current-esp32-ip>
```

Motion control, authentication, control leasing, heartbeat stop, reconnect policy, and console integration require a separate safety goal.

## Direct Chassis Motion Foundation

`chassis_motion_tcp_client.py` implements the local RCP/TCP v2 computer session. It supports authenticated `HELLO`, `PING`, `STATUS`, lease acquisition, heartbeat, enable, bounded velocity, stop, disable, and release. It sends one request at a time and never automatically retries a state-changing request whose outcome becomes unknown.

`motion_router.py` is the first flat dual-session routing layer:

```text
chassis.* → direct ESP32 TCP session
arm.*     → injected MaixCam arm session
```

It validates target/name agreement and exact payload keys, requires an injected admission callback for motion, preserves correlation IDs, and reports `automatic_retry=false`. `maixcam_arm_client.py` now provides the matching one-request-at-a-time NDJSON client for the MaixCam arm endpoint. Both are L1 candidates only; there is no GUI, persistent aggregate state store, or deployed endpoint yet.

No credential, host address, or runtime port is hard-coded in these modules. Real values belong in ignored local configuration.

## Simulator control console

Phase A adds a PySide6 desktop shell in `ui/`. It implements the approved video-first layout, independent chassis and arm controls, command journal, persistent fault list, and deterministic simulator scenarios. It deliberately owns no device socket, MediaMTX process, RTSP decoder, credential, or hardware transport.

Launch it from the repository root:

```powershell
$env:PYTHONPATH = "$PWD/src/console"
python -m ui
```

Run the non-interactive GUI construction check with:

```powershell
$env:PYTHONPATH = "$PWD/src/console"
$env:QT_QPA_PLATFORM = "offscreen"
python -m ui --smoke-test
```

`Simulator` is the only active environment in this phase. Its motion values, lifecycle transitions, and faults are synthetic and visibly recorded as such. `Hardware` mode resets every session and refuses every connection or motion request because worker-backed adapters are not implemented yet. The chassis software-stop control is not a physical emergency stop and must not be used as one.
