# Localhost Robot Console

- Status: primary operator interface
- URL: `http://127.0.0.1:8080/`
- Backend: Python standard-library HTTP server and shared device clients
- Validation boundary: L1 complete; this migration did not connect hardware

## Runtime structure

```text
Browser on 127.0.0.1
  |-- same-origin JSON API --> WebConsoleRuntime
  |                            |-- RCP/TCP v3 --> ESP32 chassis service
  |                            `-- NDJSON --> MaixCam --> UART/TCP232 --> arm
  `-- MediaMTX WebRTC page --> MaixCam video relay
```

The Python process, not the browser, owns both device sockets, request
serialization, health checks, chassis velocity refresh, state parsing, event
journal, and faults. Chassis and arm sessions have separate locks and failure
state. A fault on one route does not lock the other route.

The server binds only to loopback, serves a fixed asset allowlist, and accepts
state-changing browser requests only from its own origin. Credentials,
endpoint configuration, command payloads, and raw device replies are not sent
to the browser journal.

## Layout

```text
+-----------------------------------------------------------------------+
| Robot Console | video / ESP32 / arm | time | STOP CHASSIS            |
+---------------------------------------------+-------------------------+
|                                             | Chassis | Robot Arm     |
| Camera                                      +-------------------------+
| complete letterboxed WebRTC viewport        | status and connection   |
| future vision overlay layer                 | complete precise panel  |
+---------------------------------------------+-------------------------+
| collapsed Diagnostics: active faults + recent command events          |
+-----------------------------------------------------------------------+
```

The camera is dominant and the selected device panel uses the full right
column. Chassis and robot arm are tabs instead of two compressed cards.
Diagnostics is collapsed by default. At narrower widths the device panel moves
below the camera.

## Chassis controls

The visible lifecycle is deliberately flat:

```text
Connect -> Enable -> move/stop -> Disable -> Disconnect
```

There is no acquire/release, lease, one-shot grant, or UI unlock checkbox.
`Disable` keeps the authenticated TCP session connected; the operator may use
`Enable` again. `Disconnect` closes it.

Controls include:

- press-and-hold forward, backward, left, right, clockwise, and
  counter-clockwise buttons;
- `W/A/S/D/Q/E` equivalents while the chassis tab is active;
- independent linear and angular selectors across the configured 600 mm/s and
  800 mrad/s envelope;
- exact integer `vx`, `vy`, and `omega` entry; and
- STOP in the direction pad, exact-vector row, and application bar.

The first velocity is sent immediately. A backend worker refreshes it inside
the ESP32 hold interval, so browser scheduling is not part of the motion
contract. Pointer release, key release, page blur, or a hidden page requests
STOP. ESP32 hold expiry remains authoritative if that request cannot arrive.
Transport failures clear the held command and close only the chassis session.
Explicit ESP32 rejection is shown without dropping a healthy connection.

The UI displays requested velocity, not measured wheel velocity. Physical
feedback remains unavailable until the CAN/motor status contract provides it.

## Robot-arm controls

The independent MaixCam route exposes:

- repeatable J1-J6 relative jog, default step 2 degrees;
- repeatable X/Y/Z relative jog, default step 5 mm;
- exact six-joint absolute `MovJ` request;
- exact six-value Cartesian `MovL` request with User and Tool indices;
- gripper width from 0 to 70 mm; and
- speed and acceleration percentages.

Controls become available when MaixCam reports gateway online, controller
online, and `motion_enabled=1`. There is no chassis dependency or application
lease in YOLO/manual engineering mode. A motion call is one serialized request
and is never retried after an unknown outcome.

The compact `CURRENT` box is measurement-only. Each successful `arm.status`
sample carries six joint angles, six Cartesian pose values, User/Tool indices,
a controller sample sequence, and a controller timestamp. The browser labels
the latest sample `LIVE`; if a later read fails or the route disconnects, it
labels the retained last valid values `STALE` and keeps their PC-side age.
Target inputs never overwrite this box. Until stationary hardware verification
is complete, motion completion still reports `terminal_position_supported=0`.

## Camera and future vision

The page embeds the local MediaMTX WebRTC player from `video.webrtc_url` and
does not proxy or transcode video through the control server. The video and an
empty future overlay layer fill the same viewport. Future computer vision can
publish frame-correlated overlays without changing either command route.

The blue Video indicator means that a browser route is configured; it is not a
claim that frames are currently arriving. MediaMTX's player owns live stream
and decode feedback until a separate frame-health API is added.

The RTSP URL remains configured for future Python inference and the legacy
PySide6 decoder. The browser preview does not replace that inference input.

## Launch

Copy the template to the ignored local configuration once and fill approved
endpoints. Keep the chassis credential only in its named environment variable.

```powershell
Copy-Item config\console.example.json config\console.local.json
.\robot-console.cmd
```

Or run it explicitly:

```powershell
$env:PYTHONPATH = "$PWD/src/console"
python -m web_console --open
```

The page never connects a device automatically. Start/check the video relay
with the existing `robot` commands. The legacy `python -m ui` PySide6 surface
remains available as a temporary fallback during real-device acceptance.

The backend also appends sanitized text evidence to
`logs/console/web-events.log`. Follow it without screenshots:

```powershell
Get-Content logs\console\web-events.log -Wait
```

## HTTP interface

```text
GET  /api/state

POST /api/chassis/connect       POST /api/chassis/disconnect
POST /api/chassis/enable        POST /api/chassis/disable
POST /api/chassis/status        POST /api/chassis/stop
POST /api/chassis/motion/start

POST /api/arm/connect           POST /api/arm/disconnect
POST /api/arm/status            POST /api/arm/command

POST /api/faults/ack
```

The browser sends intents such as exact velocity or an existing arm command
name/payload. The backend validates numeric shapes and configured envelopes,
then calls the same RCP/TCP and MaixCam clients used by the desktop fallback.

## Acceptance status

L1 covers fixed-path HTTP serving, same-origin rejection, offline STOP,
credential omission, valid status mapping, full-range chassis commands,
backend-owned velocity refresh, explicit rejection behavior, arm/chassis
independence, arm vector shapes, JavaScript syntax, and the existing suites.

The next hardware acceptance is separate:

1. L2: connect and query ESP32 plus MaixCam without motion.
2. L3 chassis: Enable, six directions, exact vector, pointer release, page
   blur, hold expiry, Disable, and reconnect.
3. L3 arm: each 2-degree joint jog, each 5-mm XYZ jog, absolute inputs, and
   gripper response in confirmed YOLO mode.
4. Video: confirm WebRTC frames and 90-degree orientation while both command
   sessions remain independent.

The chassis software stop is not the physical emergency stop. Every real
motion check still requires the repository L3 gate and an on-site operator.
