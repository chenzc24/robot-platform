# Unified Control Console UI

- Status: proposed implementation baseline
- Target: Windows desktop development and operator console
- Recommended toolkit: Python 3.11+ and PySide6
- First validation mode: local simulators; real motion remains locked

Phase A is implemented as a local PySide6 simulator shell. It provides the approved layout, immutable state model, command journal, fault center, and deterministic fault scenarios. Phase B adds local-only worker foundations: ignored configuration loading, independent FIFO client sessions, copied PyAV frames, and Hardware-mode connection/status wiring. It does not contact endpoints during automated tests and does not admit hardware motion.

## 1. Purpose

The console gives one operator a clear view of video, chassis control, robot-arm control, command progress, and failures while preserving the two independent runtime routes:

```text
chassis: computer console <-> ESP32 TCP service -> CAN -> motors
arm:     computer console <-> MaixCam arm endpoint -> UART -> TCP232 -> arm LAN1
video:   MaixCam RTSP -> FFmpeg/MediaMTX or direct decoder -> computer console
```

The UI is an orchestration and debugging surface. It does not replace the ESP32 watchdog, robot controller limits, physical emergency stop, or on-site supervision.

## 2. Design principles

1. **Video is primary.** The camera occupies the largest region and keeps an overlay layer for future recognition boxes, masks, targets, and coordinate annotations.
2. **Chassis and arm remain separate.** Their connection, ownership, command lifecycle, and failure state are visible independently.
3. **Current state precedes controls.** An operator sees why a control is disabled without opening logs.
4. **One persistent fault surface.** Active faults never disappear into transient notifications.
5. **Progressive disclosure.** Common debug actions remain visible; raw envelopes, network settings, and exact target fields live in drawers or tabs.
6. **No false certainty.** Link health, command completion, physical feedback, and vision validity are different indicators.
7. **Safe by default.** Hardware mode starts disconnected and motion-locked. Reconnection never replays a previous command.

## 3. Desktop layout

The reference layout targets a 1440 x 900 or larger desktop and remains usable at 1280 x 720.

```text
+--------------------------------------------------------------------------------+
| Robot Console | SIM/LIVE | system states | session | CHASSIS SOFTWARE STOP     |
+----------------------------------------------+---------------------------------+
|                                              | Chassis                         |
| Camera                                       | connection / lease / motion     |
|                                              | directional hold controls       |
|  live image, clockwise 90 degree display     | speed limits / exact command    |
|  future detection and target overlays        +---------------------------------+
|                                              | Robot arm                       |
|  stream metrics and camera toolbar           | gateway / UART / arm states     |
|                                              | joint / Cartesian / gripper     |
+-----------------------------------------------------------+--------------------+
| Command and event journal                                 | Active faults      |
| time / target / command / lifecycle / latency / result    | cause / action     |
+-----------------------------------------------------------+--------------------+
| video age | ESP32 heartbeat | arm heartbeat | log state | local time           |
+--------------------------------------------------------------------------------+
```

At narrower widths, the video remains first. Chassis and arm become adjacent tabs below the video, and the fault surface precedes the full journal. The application does not shrink controls until labels become unreadable.

Recommended space allocation at desktop width:

- top application bar: 56 px;
- main workspace: video 64%, device controls 36%;
- device column: chassis and arm panels share the available height;
- bottom diagnostics: 220-280 px, collapsible but automatically reopened for an unacknowledged fault;
- bottom health strip: one compact line.

## 4. Application bar

The application bar contains only global context and actions:

- project and console name;
- `Simulator` or `Hardware` environment selector;
- connection summaries for video, ESP32, MaixCam gateway, and robot arm;
- coordinated-task state: `Idle`, `Blocked`, `Running`, `Fault`, or `Unknown`;
- session duration and log-recording indicator;
- persistent `Chassis software stop` action.

The stop action is deliberately named. The current arm API has no validated cancel or software-stop command, so the UI must not present a global all-device stop. A future global software stop may be added only after arm cancellation and its failure behavior pass real-device validation. The physical emergency-stop state is displayed separately when a trustworthy signal becomes available.

## 5. Camera workspace

### 5.1 Image surface

The camera workspace uses a 16:9 display with letterboxing rather than cropping. The first release applies the already observed clockwise 90-degree display transform while preserving a defined mapping from display coordinates to source-frame coordinates.

The renderer has separate layers:

1. decoded source frame;
2. display transform and scaling;
3. future vision results such as bounding boxes, labels, masks, confidence, and target points;
4. operator annotations such as crosshair, selected target, and safe-region guide;
5. temporary status overlay for stale video, reconnecting, or no signal.

An overlay is valid only when its frame identifier and timestamp match the displayed frame within a configured tolerance. Stale recognition results are hidden rather than drawn over a newer frame.

### 5.2 Visible camera controls

- connect or disconnect the preview;
- snapshot to the session log directory;
- rotate display in 90-degree steps, with clockwise 90 degrees as the initial local setting;
- fit or 1:1 view;
- show or hide overlays;
- freeze display for inspection without pausing device capture;
- stream metrics: source, resolution, frames per second, decode latency, and last-frame age.

Device camera parameters, recording, calibration, and inference-model selection belong in an expandable `Camera settings` drawer. They should not crowd the normal debug surface.

### 5.3 Video pipeline

The recommended first implementation decodes the local RTSP relay with PyAV in a dedicated worker and publishes immutable frame objects to the display. This makes future inference and overlay coordinates straightforward:

```text
local RTSP relay -> VideoWorker -> FrameBroker
                                  |-> UI renderer
                                  `-> future InferenceWorker
```

MediaMTX WebRTC remains a useful independent browser diagnostic, but embedding the browser player is not the primary console pipeline because the computer will later need decoded frames for vision.

Video loss changes vision validity to `stale` immediately, but it never blocks the independent chassis software-stop request.

## 6. Chassis panel

### 6.1 State header

The header shows:

- ESP32 address label and measured round-trip time;
- TCP state, authentication state, lease owner, lease remaining time, motion-enabled state, and last heartbeat age;
- chassis state and fault code reported by ESP32;
- explicit `Unknown` when physical motor feedback is unavailable.

Session actions are `Connect`, `Acquire`, `Enable`, `Disable`, and `Release`. Only actions legal in the current state are enabled.

### 6.2 Manual control

The default manual control is a press-and-hold directional pad:

```text
             forward
       rotate left  rotate right
left            stop            right
             backward
```

- Pressing or holding a direction emits bounded velocity commands at the configured refresh interval.
- Releasing the control, losing focus, changing tabs, or closing the window sends `STOP` and ends the hold stream.
- Keyboard bindings may use `W/A/S/D` for translation and `Q/E` for rotation only while the chassis panel owns keyboard focus.
- Exact `vx`, `vy`, `omega`, and hold duration fields are available in an `Advanced` section.
- Linear and angular speed-limit controls show units and remain capped by local ESP32 limits.
- The latest requested velocity and reported state are shown separately.

The panel never treats a successful TCP write or `DONE` from the current local candidate as proof of physical wheel motion. Measured feedback is added only when the CAN/motor contract supplies it.

### 6.3 Enablement gate

Velocity controls require all of the following:

- hardware or simulator environment selected deliberately;
- ESP32 session connected and authenticated;
- valid control lease owned by this console;
- fresh heartbeat;
- motion enabled by ESP32;
- no blocking chassis, arm-position, or coordinated-task fault;
- operator has unlocked manual motion for the current session.

`Chassis software stop` remains available whenever an ESP32 socket can be opened or is already open, even when ordinary motion controls are locked.

## 7. Robot-arm panel

### 7.1 State header

The arm header exposes the complete route rather than one misleading online light:

```text
computer session -> MaixCam endpoint -> UART/TCP232 -> arm LAN1 project
```

Each hop can be `Online`, `Degraded`, `Offline`, or `Unknown`. The panel also shows arm controller mode, current task lifecycle, last status age, and whether measured pose feedback is available.

### 7.2 Control tabs

The engineering UI provides five compact tabs:

1. **J1-J6 jog**: repeatable `- / +` movement with a default 2-degree step.
2. **XYZ jog**: repeatable user-coordinate `- / +` movement with a default 5-mm step.
3. **Absolute J**: six target joint-angle fields and `Execute joint move`.
4. **Absolute XYZ**: `x`, `y`, `z`, `rx`, `ry`, `rz` and `Execute linear move`.
5. **Gripper**: requested width in millimetres and `Set gripper width`.

Current and target values use separate rows. Until the arm returns measured pose, current values show `Unavailable`; they must never echo the command target as measured state.

Named actions such as `Safe pose`, `Pick`, and `Place`, queue cancellation, and
trajectory editing remain future controls.

### 7.3 Arm command gate

In YOLO/manual engineering mode an arm motion command requires only:

- computer-to-MaixCam session online;
- MaixCam-to-arm non-motion readiness handshake fresh;
- arm controller and project ready;
- no command already running;
- the controller project and MaixCam endpoint both reporting motion enabled.

It does not require an application lease, one-use permission, repeated enable,
UI unlock checkbox, or ESP32/chassis state. Message shape and finite numeric
validation remain active. Dobot controller limits, collision handling, recovery,
and emergency stop remain authoritative.

The command button changes to lifecycle status but does not become a second cancel control. `UNKNOWN` is terminal from the console's point of view: the UI locks further non-idempotent arm actions and asks the operator to inspect the device rather than retrying automatically.

## 8. Command journal and fault center

### 8.1 Command journal

Every request receives one row with:

- local timestamp;
- target and route;
- command name;
- message or sequence identifier;
- lifecycle state;
- elapsed time;
- concise result or error code.

Selecting a row opens a detail drawer containing sanitized request and response envelopes, all lifecycle transitions, timestamps, and transport evidence. Secrets are never written to the journal.

The journal distinguishes:

- request accepted by the local UI;
- bytes sent;
- endpoint acknowledgement;
- endpoint running state;
- endpoint terminal result;
- measured physical completion, if separately available.

### 8.2 Active faults

Active faults remain visible until the underlying state clears. Each item contains severity, source, code, first and latest occurrence, concise explanation, and one safe next action. Available actions are:

- `Inspect`, which opens related state and log evidence;
- `Acknowledge`, which records operator awareness but does not clear device state;
- `Recheck`, which performs only an idempotent status query;
- `Copy details`, which copies sanitized diagnostics.

Fault severity uses text and an icon in addition to color:

- `Info`: noteworthy transition;
- `Warning`: degraded but safe to remain idle;
- `Fault`: operation blocked;
- `Unknown`: outcome cannot be established and manual inspection is required.

Transient notices may appear briefly, but faults and unknown outcomes never rely on toast notifications alone.

## 9. Debugging and connection controls

A right-side settings drawer or compact menu provides infrequent controls:

- current environment and ignored local configuration source;
- ESP32 and MaixCam host labels, ports, and timeout values;
- connect, disconnect, and idempotent status refresh for each session;
- video relay start, stop, restart, and diagnostics through the existing protected computer CLI;
- MaixCam service status and log retrieval;
- simulator fault injection for disconnect, timeout, rejection, fault, and unknown outcome;
- export of the sanitized session journal.

Device deployment, flashing, WebREPL, SSH shell access, TCP232 configuration, and DobotStudio project deployment remain development tools rather than ordinary console buttons. The console may link to their documented commands, but it does not silently perform maintenance writes.

## 10. UI-to-runtime boundary

Widgets must not call sockets or decode video on the UI thread. The proposed boundary is:

```text
PySide6 views
    | intents and immutable view state
ConsoleController
    |-- SafetyGate
    |-- StateStore
    |-- CommandJournal
    |-- ChassisSessionWorker -> ChassisMotionTcpClient -> ESP32
    |-- ArmSessionWorker ----> MaixCamArmClient ------> MaixCam
    `-- VideoWorker ---------> PyAV / local RTSP relay
```

Each worker owns exactly one blocking resource and communicates with the controller through queued signals. A slow video decoder cannot delay a heartbeat, and an arm request cannot block the chassis stop path.

The state store keeps separate domains:

- `connection`: socket and transport health;
- `service`: reported process state;
- `control`: authentication, ownership, lease, and admission;
- `task`: command lifecycle;
- `physical`: pose, velocity, limit, and feedback evidence;
- `vision`: frame and inference freshness;
- `fault`: active and historical faults.

UI controls subscribe to derived view state. They do not infer readiness from button history.

## 11. Binding to current interfaces

| UI intent | Existing computer-side call | Binding status |
|---|---|---|
| ESP32 ping/status | `ping()`, `status()` | available for L1; real v2 endpoint not deployed |
| Chassis ownership | `acquire()`, `heartbeat()`, `release()` | available for L1 |
| Chassis motion gate | `enable()`, `disable()` | available for L1; real motion remains disabled |
| Chassis manual request | `velocity()` | available for L1; no measured wheel completion |
| Chassis software stop | `stop()` | available for L1; physical validation pending |
| Arm ping/status | `ping()`, `status()` | available for L1; endpoint not deployed |
| Arm joint target | `move_joint()` | available for L1; default admission rejects motion |
| Arm Cartesian target | `move_linear()` | available for L1; default admission rejects motion |
| Gripper width | `gripper()` | available for L1; device capability unverified |
| Video preview | local RTSP relay and MediaMTX | real link previously passed; UI decoder not implemented |
| Arm cancel/software stop | none | must not be offered as working control |
| Measured chassis/arm completion | none | display `Unavailable` or `Unknown` |

The synchronous clients require worker wrappers, connection lifecycle management, timeouts, and state normalization before they are safe to bind to widgets. The existing `DualSessionMotionRouter` may remain the command dispatch boundary after the controller has performed admission checks.

## 12. Normal operator workflows

### 12.1 Simulator development

1. Start the console in `Simulator` mode.
2. Connect video, chassis, and arm simulators independently.
3. Exercise every control and lifecycle transition.
4. Inject disconnect, rejection, timeout, fault, and unknown outcomes.
5. Verify that controls lock, no command is replayed, and the journal preserves evidence.

### 12.2 L2 hardware connection without motion

1. Select `Hardware`; all motion remains locked.
2. Connect video and confirm frame freshness.
3. Connect ESP32 and query status without acquiring or enabling motion.
4. Connect the MaixCam arm endpoint and query the complete arm route.
5. Disconnect and reconnect each link independently and confirm old commands are not restored.

### 12.3 Later single-device motion

Only after the current L3 safety gate, deploy and validate one device at low
speed. The arm engineering UI does not add a session unlock; chassis and arm
remain independent during manual debugging. Coordinated behavior belongs to a
separate L4 orchestrator.

## 13. Visual language

- Default dark theme with a future light equivalent; use Windows-native Segoe UI or Inter.
- Neutral charcoal surfaces, one restrained blue action accent, green only for verified readiness, amber for degraded state, and red only for blocking faults or stop actions.
- Status always combines icon, label, and color.
- Eight-pixel spacing rhythm, compact 36-40 px desktop controls, 10-12 px corner radius, and minimal shadow.
- Numbers use tabular figures; units remain adjacent to values.
- Motion buttons are never icon-only. The most dangerous actions include explicit verbs and targets.
- The main view contains no decorative charts or summary cards that do not help operate or diagnose the robot.

## 14. Implementation phases

### Phase A: UI shell and simulators, L1

- PySide6 application shell, theme, layout, and navigation;
- immutable view-state models and command journal;
- video placeholder and overlay coordinate model;
- chassis, arm, and fault panels with all hardware motion locked;
- simulator adapters and deterministic lifecycle/fault scenarios.

### Phase B: current interface adapters, L1

- worker-thread wrappers for the existing chassis and arm clients, with a separate FIFO owner for each session;
- explicit connection, safe `PING`/`STATUS`, disconnect, terminal fault propagation, and no automatic retry;
- direct RTSP decode worker that copies RGB frames into Qt-owned images, applies the UI display rotation, and supports configured local snapshots;
- secret-free settings template with ignored local overrides;
- Hardware-mode UI wiring for configuration-gated connection/status/preview only. No lease, heartbeat, enable, velocity, arm primitive, or chassis software-stop call is admitted.

Bounded polling, any motion admission, deployed endpoint tests, and heartbeat scheduling remain later work. They must not be inferred from this L1 foundation.

The Phase B hardening pass accepts only the exact current status schemas: ESP32 RCP/TCP v2 `STATE`, and the terminal MaixCam `arm.status` lifecycle envelope containing the RPA2 arm-service state. Invalid status leaves the last trustworthy state unchanged and creates a persistent fault. Video frames are copied before crossing into the GUI thread; decoder failure, bounded shutdown, repeat start/stop, low frame rate, and snapshot path rejection are covered with local fakes. Snapshots are constrained below the local `logs/` root. Hardware-mode controls remain default-deny even if a reported endpoint says motion is permitted.

### Phase C: hardware connectivity, L2

- bind the deployed ESP32 and MaixCam endpoints with motion disabled;
- validate status freshness, reconnect, timeout, and fault presentation;
- validate video independence from both control sessions.

### Phase D: single-device motion, L3

- enable bounded chassis control after CAN and stop validation;
- enable arm primitives only after limits, terminal evidence, and cancel policy are validated;
- keep each device's unlock and acceptance independent.

### Phase E: coordinated operation and vision, L4

- add inference worker and time-correlated overlays;
- add chassis-stopped and arm-safe interlocks;
- add high-level task sequencing after single-device failure behavior is proven.

## 15. Acceptance criteria for the first UI release

- The console remains responsive during video loss, socket timeout, and a long arm request.
- Chassis stop handling is not queued behind video or arm work.
- No state-changing command is retried automatically after an uncertain outcome.
- Every disabled control presents a concise reason.
- Simulator and hardware modes are visually unmistakable.
- Video, ESP32, MaixCam, and arm state can disagree without being collapsed into one green indicator.
- Faults remain visible and traceable to sanitized command evidence.
- The interface restores no chassis lease, velocity, arm target, or pending action after restart.
- At 1280 x 720, video and both device panels remain reachable without clipped essential actions.
- Real motion remains impossible until its separate safety and validation gate is satisfied.

## 16. Decisions to confirm before implementation

1. Accept PySide6 as the desktop toolkit and PyAV as the first video decoder.
2. Accept the video-left, controls-right, diagnostics-bottom layout.
3. Accept a chassis session unlock and an independent arm YOLO/manual mode.
4. Accept that the initial arm panel exposes joint, Cartesian, and gripper targets only; named actions arrive after their protocol exists.
5. Accept that the current top-level stop is explicitly chassis-only until an arm cancel contract is implemented and validated.
