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
| PC AprilTag observation overlay             | complete precise panel  |
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

Direction buttons and keys are momentary: release ends the input. Only
`APPLY & HOLD` keeps the exact vector active without keeping a button pressed.
A direction input replaces an exact hold; releasing that direction does not
restore the old vector. Reapplying an exact vector updates it.

The first velocity is sent immediately. The PC refresh worker owns subsequent
device VELOCITY packets. Every start echoes the current opaque motion epoch;
STOP, Disable, disconnect and replacement invalidate older work. STOP invalidates
before waiting for device I/O, so neither an in-flight start nor a queued refresh
can restore the cleared command after STOP completes. The browser discards late
input replies and waits for outstanding STOPs before starting a new direction.

While an input is active (momentary or exact hold), the page automatically sends
presence every 200 ms. This does not send a velocity or create a new motion.
The PC expires input after 1000 ms without accepted presence, clears the refresh
state and requests STOP. Expired or old-epoch presence cannot revive it. Release,
pointer cancellation/capture loss, page blur, pagehide and a hidden page request
STOP immediately and cease presence. A lost STOP HTTP request or closed page
therefore cannot leave the PC renewing velocity indefinitely. A missed physical
input event cannot be inferred from presence alone; the pointer path also checks
for movement events with no button pressed, and blur/capture handlers cover the
usual focus-loss cases.

ESP32 still stops locally after its last VELOCITY hold expires (up to 500 ms).
Its watchdog alone cannot cover browser loss while the PC continues refreshing;
the browser-presence check closes that gap. These are software timing bounds,
not hard real-time or physical stop feedback. They add no operator gate, lease,
acquire/release step, repeated Enable or changed device protocol/speed limit.
Transport failures clear input and close only the chassis session. An explicit
refresh rejection is logged, clears input and requests STOP while retaining a
healthy connection. A failed start or refresh is never automatically retried.

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

RPA2 speed/acceleration (1..100%) and gripper width (0..70 mm) are integer
fields. The web backend accepts integral JSON numbers such as `20` or `20.0`
but emits `20` on the wire. Fractional values for these fields are rejected
locally without rounding. Joint and Cartesian coordinates retain decimals.

Only a terminal `DONE` is logged as completed. `REJECTED` and `FAULT` preserve
their device error codes in the HTTP error, journal and fault panel without
disconnecting an otherwise healthy arm link or affecting the chassis. Missing
or untrustworthy motion results are `UNKNOWN`, not success, and are not retried.
Controller `last_error` also appears in the fault panel. Repeated status polls
do not flood the log or reset acknowledgement; a newly failed operator command
does re-open its fault. Historical faults remain visible after recovery and do
not constitute an extra motion-enable gate. Controller `DONE` still does not
prove measured terminal position or successful gripping.

The compact `CURRENT` box is measurement-only. Each successful `arm.status`
sample carries six joint angles, six Cartesian pose values, User/Tool indices,
a controller sample sequence, and a controller timestamp. The browser labels
the latest sample `LIVE`; if a later read fails or the route disconnects, it
labels the retained last valid values `STALE` and keeps their PC-side age.
Target inputs never overwrite this box. Until stationary hardware verification
is complete, motion completion still reports `terminal_position_supported=0`.

## Request timing and independent health workers

The shared MaixCam client gives PING and STATUS a 5000 ms request TTL. Its
absolute send/response deadline is that TTL plus a 1-second transport margin;
partial reads and lifecycle messages do not restart the budget. The configured
3-second connection timeout is separate and is restored after the request.
Motion calls retain their existing 60-second TTL. No state-changing command is
automatically retried after a timeout or unknown outcome.

The web backend runs chassis health and arm status in separate workers. A slow
arm query therefore does not block chassis PING/STATUS. Arm polling waits
500 ms after each completed query and skips an occupied arm route instead of
accumulating polls. This is request-driven feedback, not high-frequency or
in-motion telemetry. ESP32 heartbeat-stop and velocity-hold limits are unchanged.

## Camera and AprilTag vision

The page embeds the local MediaMTX WebRTC player from `video.webrtc_url` and
does not proxy or transcode video through the control server. When explicitly
enabled, the PC opens the local RTSP route independently, detects known AprilTag
36h11 corners, estimates the board pose, and publishes the latest observation
through the existing state API. A transparent canvas draws ID-labelled boxes
with the same letterbox and 90-degree display transform as the preview.

The blue Video indicator means that a browser route is configured; it is not a
claim that frames are currently arriving. MediaMTX's player owns live stream
and decode feedback until a separate frame-health API is added.

The RTSP URL is shared by the AprilTag worker and legacy PySide6 decoder. The
browser preview does not replace that inference input. WebRTC and inference are
separate receivers and are not frame-synchronized in v1; overlays may lag while
the camera moves. Vision output is observation-only and never starts a device
session or issues motion. See [AprilTag localization](apriltag-localization.md).

When schema 5 localization is enabled, the backend invalidates the old scalar
rail position before any nonzero PC chassis-motion request, waits after the
ESP32 again reports `enabled_stopped`, and locks a new position/JSON-offset
generation from a bounded window of stable accepted poses. `GET /api/state`
exposes the result under `localization`. This is an orchestration interface for
a future coordinate task, not an added gate on the independent manual arm
controls. See the
[localization lock state machine](localization-state-machine.md).

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

`MOTION` lines record epoch, input mode, clear reason and the number of refreshes
since start. Per-refresh successes do not flood the operator journal. Internal
clear means the PC stopped renewing; only the subsequent STOP result describes
the device command response, and neither is measured motor feedback. The state
snapshot includes `chassis.motion` with the same diagnostics and remaining input
time. The compact requested-vector label includes IDLE / MOMENTARY / HOLD.

After installing this PC update, restart the backend and reload the page as a
pair. New assets shown by an older running backend disable motion controls and
display a restart message. An old page against the new backend has its metadata-
free motion starts rejected; reload it. No ESP32 or MaixCam redeployment is needed.

## HTTP interface

```text
GET  /api/state

POST /api/chassis/connect       POST /api/chassis/disconnect
POST /api/chassis/enable        POST /api/chassis/disable
POST /api/chassis/status        POST /api/chassis/stop
POST /api/chassis/motion/start
POST /api/chassis/motion/keepalive

POST /api/arm/connect           POST /api/arm/disconnect
POST /api/arm/status            POST /api/arm/command

POST /api/localization/relocalize

POST /api/faults/ack
```

The browser sends intents such as exact velocity or an existing arm command
name/payload. The backend validates numeric shapes and configured envelopes,
then calls the same RCP/TCP and MaixCam clients used by the desktop fallback.

For web API motion, read `chassis.motion.epoch` from `GET /api/state`. A start
contains integer `vx_mm_s`, `vy_mm_s`, `omega_mrad_s`, `input_mode` (`momentary`
or `hold`) and that `motion_epoch`. Its successful state contains the new epoch.
Send `{ "motion_epoch": "<active epoch>" }` to the keepalive route while the
input remains active; send STOP when it ends. STOP needs no epoch and always
invalidates older starts. Optional STOP reasons are allowlisted for diagnostics.
Keepalive does not reconnect, Enable, change a vector or retry a motion. These
fields exist only between the web caller and PC; device RCP/TCP remains v3.

## Acceptance status

L1 covers fixed-path HTTP serving, same-origin rejection, offline STOP,
credential omission, valid status mapping, full-range chassis commands,
backend-owned velocity refresh, explicit rejection behavior, arm/chassis
independence, arm vector shapes, JavaScript syntax, and the existing suites.

Hold-release regression checks (all offline):

```powershell
python -m unittest discover -s tests/console -p test_chassis_hold_lifecycle.py
node --test tests/console/test_chassis_input.js
```

These cover deterministic start/STOP and refresh/STOP interleavings, Disable and
disconnect cancellation, epoch rejection, presence expiry, log diagnostics, HTTP
routing and actual JavaScript pointer/key bindings using fake events/requests.
They do not substitute for physical release and stopping-distance acceptance.

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
