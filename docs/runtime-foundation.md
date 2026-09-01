# Device running time base

- Status: Local L1 baseline, no real machine deployed
- Application: ESP32 security application, MaixCam video service and follow-up device service
- Shared contracts:`protocol/runtime-status.schema.json`

## 1. Languages and borders

- Add running codes, notes, docstring, identifier, log keys, event name and error code in English.
- Project design, on-site operation and security document available in Chinese.
- `src/esp32/legacy/` It's a byte history snapshot, no translation, no formatting, no deployment source.
- Local `secrets.py`, `device_config.py`And compile caches that do not enter Git, workspace validation tools do not read secret files.

## 2. Structured status compacts

ESP32, MaixCam and the follow-up console share the following mandatory fields:

```json
{
  "schema_version": 1,
  "event": "service_ready",
  "device": "maixcam",
  "subsystem": "video",
  "state": "ready",
  "sequence": 2,
  "uptime_ms": 1250,
  "error_code": null,
  "detail": {}
}
```

The service life cycle status is:

```text
starting / idle / ready / running / stopping / stopped
disconnected / safe_idle / fault / estop
```

These are service health and safety, not equal to future robotic missions. `ARMED/RUNNING/COMPLETED` Business status. Both have to use different fields to avoid the misperception of "service is running" as "motion is on."

## 3. ESP32 Module

| Module | Duties | Current hardware behaviour |
|---|---|---|
| `main.py` | Group entrance | None |
| `application.py` | Operating mode doors and life cycle | Only `SAFE_IDLE` |
| `esp_runtime_status.py` | MicroPython compatible JSON status event | None |
| `control_lease.py` | Single controller, timeout, renewal and release | None, not connected to chassis parking |
| `chassis_control.py` | Baseboard status machine, limit bands and failure rollback | It's only possible by injecting MotoBus. |
| `motor_bus.py` | Can frame encoding, sending, failure count and batch rollback | It's only possible by injecting Can. |

`ControlLease` It's only a protected language that has been tested. Until the official chassis service is completed, the lease expires without automatically calling the real parking, without claiming that the heartbeat has been stopped.

## 4. MaixCam video module

```text
rrtsp server.py CLI, signal and process life cycle
  └─ video_service.py
       Ideas - RtspVideoService Status, Rollback and Camera Ownership
       └ - MaixRtspBackend MaixPy camera and RTSP thin adapter

maix runtime status.py structured state
Resources within the process
Start.sh / stop.sh / status.sh PID at validation and running entrance
```

Rules of protection:

- Import CLI and Service Module Not Import `maix`, so they won't use UART or cameras for local tests.
- Only `MaixRtspBackend` Import when Construct `maix`, and release the system default UART0 monitor immediately.
- Video services must be successfully accessed `camera` Create backend after ownership.
- Release ownership when the anomaly is activated or stopped, record the error code and enter `fault`.
- Shell scripts check if PID really belongs to the RTSP program on this item before sending the termination signal.

## 5. VS Code entrance

Change only in current cycle `.vscode/tasks.json`,do not change the user 's unsubmitted `.vscode/settings.json` Button Configuration.

New main entrance:

- `Robot: Local preflight`: Unequipped syntax, workspace, contract and all unit tests.
- `Robot: Run all local tests`ESP32, MaixCam and shared compact test.
- `Robot: Check live links`: Users run manually later, checking only ESP32 WebREPL port and MaixCam SSH.
- `MaixCam Video: Start development session`: Upload, start, computer relay and actual frame detection; still manual exit before running `num`.
- `MaixCam Video: Status`, `Show recent log`, `PC relay status`Declining.
- `Robot: Stop PC services`: Stop only FFmpeg and MediaMTX, not device RTSP.

Add the flat daily entrance:

- `Robot: Connect`: Two devices were found, the missing MaixCam RTSP and the computer relay were activated, and the health services remained intact.
- `Robot: Status`: Three-tier summary only.
- `Robot: Details`: Perform all checks, error codes and suggestions for next steps.
- `Robot: Disconnect`: Stop computer relay only.

These tasks call the repository root directory. `robot.cmd`The same CLI provides protection. `ps/logs/stop/restart/kill/reboot`Maintain commands, but do not provide any PID to kill; ESS32 restarts locking until it's secure.

This wheel does not add motors, chassis speed or robot arm movement shortcuts.

## 6. Receiving and inspection boundaries

This round will only confirm:

- Share status fields and devices to achieve consistency in local testing.
- The ESP32 security entrance still does not initiate motor hardware.
- Control the lease, camera ownership, state feedback and failure rolls back through false object testing.
- New deployment lists and scripts have not been implemented on MicroPython or MaixCam.

Once onboard, the user must set an additional L2 target, verify import, file deployment, structured log, camera startup and recovery; do not deploy ESP32 mode before L2.
