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

## Unified control console

Phase A adds a PySide6 desktop shell in `ui/`. It implements the approved video-first layout, independent chassis and arm controls, command journal, persistent fault list, and deterministic simulator scenarios.

Phase B adds local runtime foundations without admitting hardware motion: separate FIFO background sessions for the existing direct ESP32 and MaixCam-arm clients, a copied-frame PyAV RTSP worker, and a secret-free local configuration loader. No connection starts automatically and no action is retried automatically. In `Hardware` mode, the console may request an explicit connection, `PING`/`STATUS`, a disconnection, preview frames, and a local snapshot; lease, enable, velocity, arm movement, and chassis software stop remain disabled or rejected.

The console accepts only the current exact ESP32 RCP/TCP v2 `STATE` schema and the current terminal `arm.status` lifecycle/RPA2 state schema. A malformed, incomplete, or inconsistent status response becomes a persistent fault and never enables a control. Snapshots use a configured relative directory below the local `logs/` root, such as `snapshots/session-a`; absolute paths and traversal outside that root are rejected.

Launch it from the repository root:

```powershell
$env:PYTHONPATH = "$PWD/src/console"
python -m ui
```

To prepare an optional local runtime configuration, copy `config/console.example.json` to the ignored `config/console.local.json`, then fill only endpoint values that have been separately approved for an L2 non-motion test. Credentials remain environment variables and must not be added to either JSON file. The default launch does not require this file; without it, `Hardware` mode displays no real connection.

Run the non-interactive GUI construction check with:

```powershell
$env:PYTHONPATH = "$PWD/src/console"
$env:QT_QPA_PLATFORM = "offscreen"
python -m ui --smoke-test
```

`Simulator` values, lifecycle transitions, and faults are synthetic and visibly recorded as such. The chassis software-stop control is not a physical emergency stop and must not be used as one. Opening an L2 connection or any L3 motion path requires a separate approved hardware goal and the applicable safety gate.
