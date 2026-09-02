# Migrate the Unified Console to Localhost Web

- Status: `complete`
- Responsible: `agent`
- Highest validation level: `L1`; no device connection or real motion

## Objective

Replace the primary PySide6 operator surface with a compact localhost web
console while preserving the validated PC-to-ESP32 and PC-to-MaixCam backend
interfaces. The page must show the camera prominently, provide complete and
precise chassis and arm controls, expose concise status/fault evidence, and
avoid unnecessary descriptions, borders, and diagnostic clutter.

## Initial workspace state

```text
## main...origin/main
 M .vscode/settings.json
```

The `.vscode/settings.json` change is user-owned and must remain untouched,
unstaged, and uncommitted. Work proceeds on `target/web-console-migration`.

## Editable scope

- new pure-Python shared console runtime primitives under `src/console/`
- new localhost server/runtime and static web assets under
  `src/console/web_console/`
- PySide6 runtime imports needed to share the same backend primitives
- console configuration schema/template and ignored local migration
- focused console/server tests and development launch integration
- console/overall documentation, this goal plan, and `plan/log.md`

## Read-only scope

- ESP32, MaixCam, robot-arm, TCP232, CAN, protocol wire formats, device-local
  code/configuration, credentials, endpoints, physical limits, and raw resource
  archives
- `.vscode/settings.json`

## Architecture

```text
browser 127.0.0.1
  |-- same-origin HTTP state/commands --> Python WebConsoleRuntime
  |                                      |-- RCP/TCP v3 --> ESP32
  |                                      `-- NDJSON --> MaixCam --> arm
  `-- configured MediaMTX WebRTC page --> local video relay
```

- The Python backend owns sockets, serialization, 500 ms chassis health
  polling, held-velocity refresh, disconnect handling, command journal, and
  fault state.
- The browser never owns a motion or health timer. Pointer/key release and page
  loss request stop, while the ESP32 velocity hold and connection-health
  timeout remain authoritative if the page disappears.
- The HTTP server binds loopback only, serves fixed local assets, validates
  same-origin state-changing requests, and never exposes credentials.
- MediaMTX carries video directly to the browser. The control server does not
  proxy or transcode frames; future vision results can be drawn in a separate
  overlay layer.

## Experience

- one compact top bar with mode, three link indicators, and chassis stop
- camera-dominant workspace with a complete letterboxed viewport
- one full-height device panel using Chassis/Arm tabs
- chassis direction pad plus exact `vx/vy/omega` entry and full 600/800 range
- arm Joint/XYZ/Absolute/Gripper tabs using existing MaixCam commands
- one collapsible diagnostics drawer containing faults and recent events
- no marketing copy, instructional paragraphs, decorative cards, or duplicate
  state labels in the normal viewport

## Expected work

1. Extract device factories/dispatchers/results from the Qt runtime into a
   pure-Python module reused by both frontends.
2. Implement a loopback HTTP API and stateful runtime with independent chassis
   and arm locks, backend-owned health and held-motion loops, and sanitized
   state/events/faults.
3. Build the compact responsive HTML/CSS/JavaScript control surface and bind
   every visible action to an API endpoint.
4. Add a launch command, migrate local video browser URL configuration, update
   documentation, and keep the legacy PySide6 console available only as a
   fallback during the migration.
5. Validate backend calls with fakes, HTTP/origin/path behavior, static build
   content, Qt regression compatibility, and browser interaction on localhost.

## Validation

- focused web runtime/API tests with fake chassis and arm clients
- existing console, protocol, ESP32, MaixCam, robot-arm, and development tests
- Python/JavaScript syntax checks and PySide6 offscreen smoke
- localhost HTTP response plus browser layout and interaction inspection
- `git diff --check`, secret/scope review, and final Git status

## Deployment boundary

The implementation and browser preview may run locally in simulator/fake mode.
It must not connect to real device endpoints during automated or visual tests.
No hardware write or movement is authorized by this goal.

## Intent to submit

```text
feat(console): migrate operator UI to localhost web
```

## Actual result

- Added a loopback-only static server and JSON API with no additional runtime
  dependency.
- Extracted configuration, status parsing, factories, and dispatchers into
  pure-Python modules shared by the web and PySide6 frontends.
- Implemented independent ESP32 and MaixCam-arm sessions, backend-owned chassis
  hold refresh, status polling, exact arm/chassis validation, fault state, and
  a sanitized text event log.
- Implemented the compact camera-first browser layout with complete chassis
  direction/exact-vector control and complete joint/XYZ/absolute/gripper arm
  control. The MediaMTX route is embedded directly and starts rotated 90
  degrees.
- Kept the prior PySide6 UI as a migration fallback. No wire protocol, device
  runtime, endpoint, credential, CAN setting, arm project, or physical limit
  was changed.

## Validation result

- 236 L1 tests passed across `console`, `dev`, `esp32`, `maixcam`, `protocol`,
  and `robot_arm` suites using Python 3.13.
- Python compilation and `node --check` passed for the new backend and browser
  code.
- Local HTTP root and state returned 200 with both device sessions offline.
- Browser inspection at 1280 x 720 confirmed the complete camera/chassis
  layout, six visible joint-jog rows, all 14 absolute pose/tool inputs,
  collapsible diagnostics, enabled STOP, disabled offline motion, 90-degree
  initial display class, and no console errors.
- No device session was opened, no deployment was performed, and no motion was
  requested. L2/L3 acceptance remains pending.
- `git diff --check` passed before final staging. The user-owned
  `.vscode/settings.json` remained untouched and unstaged.
- Implementation commit: `c58cd54` on `target/web-console-migration`.
