# Repair chassis hold/release lifecycle

- Status: implemented, pushed and PC backend replaced; L2 passed, operator L3 pending
- Baseline: 58cc8d9 on target/arm-ui-command-fixes
- Risk: motion-affecting PC code; L1 validation now, attended L3 acceptance later.
- Request: fix confirmed PC hold resurrection and stale refresh after STOP.

## Workspace and ownership

Preserve user .vscode/settings.json. Existing uncommitted plan/log.md entries
and the XYZ/hold diagnostic directories are this agent's prior diagnostic work.
Keep the XYZ diagnosis out of this implementation commit. Include only the hold
diagnosis and this goal's factual log sections when staging the shared log.

Editable: src/console/web_console/{runtime.py,server.py,static/app.js,
static/overrides.css},
tests/console/test_web_console.py, tests/console/test_chassis_hold_lifecycle.py,
tests/console/test_chassis_input.js, docs/console/control-console-ui.md,
this plan, the hold diagnosis plan and scoped sections of plan/log.md.
Ignored tmp/ may hold diagnostic-only helpers. All other sources/configuration,
raw resources, protocol, device files and XYZ diagnostic records are read-only.

Shared dependencies: existing chassis client, RCP/TCP v3, ESP32 hold watchdog,
separate arm/video workers. Device protocol, firmware, limits, authentication,
Enable/Disable UI lifecycle and the architecture remain unchanged. Only the
loopback web input contract gains internal epoch/mode/presence metadata; neither
MaixCam nor ESP32 nor arm adapters need a coordinated device deployment.

## Design and validation

- Serialize velocity dispatch/state publication under chassis I/O; invalidate
  pending starts and refreshes immediately on STOP, Disable, disconnect/error.
- Browser echoes an opaque motion epoch to reject starts arriving after STOP;
  late responses must not resurrect input state. Direction input replaces exact
  hold and always ends on release; no additional operator authorization steps.
- Backend refresh requires recent browser input presence (automatic keepalive).
  This bounds a lost release/page-close request while preserving explicit HOLD.
  Keepalive cannot create/revive motion or reissue a failed start.
- Expose/log internal motion mode, epoch, clear reason and refresh count; avoid
  per-tick journal noise. Correct the misleading undelivered-STOP fallback text.
- Deterministic fake-client tests: delayed start, queued/stale refresh, STOP,
  Disable/disconnect/reconnect, presence expiry, late keepalive, error cleanup,
  full-envelope input and state diagnostics. JS tests execute real input handlers
  with fake DOM/fetch/timers and no real endpoints. Test HTTP metadata routing.
- Run existing console/device regressions, Python/JS syntax, diff/secret review.

No hardware motion, deployment, restart, automatic connection or Enable this
turn. Live backend replacement requires operator coordination after L1; avoid
silently swapping browser assets against the still-running old backend. Use
versioned/paired asset loading and compatibility detection where necessary.

Commit/push intent: scoped fix on target/chassis-hold-release-fix, no main merge;
retain unrelated user changes and the uncommitted XYZ diagnosis. Document L3 as
not run and report that the running process still needs replacement.

## Actual results

- Added epoch invalidation, I/O-serialized motion publication/refresh, and
  STOP/Disable/disconnect cancellation. Queued old work is rejected; a late
  response cannot re-arm either backend or browser input. Status publication
  is also serialized so a late poll cannot overwrite a completed stop/disable.
- Direction pointer/key input is momentary; exact HOLD is explicit and can be
  reapplied with changed values. Switching from exact HOLD to a direction stops
  the old input. Pointer ownership, cancel/lost-capture, button-free movement,
  pagehide/blur/hidden and overlapping STOP completion are covered.
- Active browser input sends automatic 200 ms presence; PC permits refresh only
  within 1000 ms of accepted presence. Expired/stale presence cannot create or
  revive motion. This bounds a lost STOP request/browser disappearance, not an
  arbitrary physical event that the browser itself never observes. No new user
  authorization steps, device protocol, speed/hold limits or device writes.
- Added motion epoch/mode/reason/refresh-count diagnostics without per-tick event
  noise. Log I/O failure cannot prevent STOP; sanitized log_error is in state.
- Old-page/new-backend starts lacking metadata are rejected. New assets served
  by the old backend disable motion with a restart message. Backend and page
  must be replaced/reloaded together; no live service has been restarted.
- L1: 99 console tests (including 19 new lifecycle cases), 55 ESP32 tests,
  25 dev-tool tests, and 13 Node tests executing real JS input bindings passed.
  Python compilation, JavaScript syntax and git diff --check passed.
- No hardware control calls or real movement. The HTTP regression server uses
  injected fake clients on an ephemeral loopback port. Physical release and
  stopping-distance L3 acceptance remain unperformed. Asked the operator whether
  the PC backend may now be replaced; do not infer approval from test completion.
- Full owned diff reviewed; only scoped files will be committed/pushed. User
  settings and unrelated XYZ diagnosis/log entry remain outside the commit.

## Approved PC backend replacement

The operator explicitly requested backend restart after the repair was pushed
as e2d668f. Scope now includes replacing only the identified PC web process using
the existing ignored credential-preserving launcher, its generated local logs,
and L2 non-motion reconnection/status checks. No source or device changes needed.

Preflight: localhost:8080 owner PID 24504, virtual-environment launcher parent
38004; old API lacks chassis.motion. Chassis reports enabled_stopped with zero
requested vector; arm route offline/idle. MediaMTX listener PID 15684 is excluded.
Current dirty paths remain user settings and this agent's separate XYZ diagnostic
plan/log record; preserve them outside this scoped record commit.

Use existing disconnect to STOP/Disable and close the chassis session, verify
offline before terminating only the identified backend, then launch hidden with
the preserved credential in the child environment (never print it). Reconnect
only the previously active chassis route, read status, and require disabled/idle
with the new motion metadata. Leave arm offline as found; do not reset alarms,
send motion/Enable, restart device/video services or write device files. Page
reload is required. Recovery is the existing local launcher/configuration; if
startup fails, retain chassis disconnected/disabled and report the error.

Validation is L2 only; physical hold/release acceptance remains operator L3 work.
Record actual restart results, diff/status and push only this plan/log update.

### Replacement results

- The old backend acknowledged chassis disconnect and reported offline/disabled;
  a second GET confirmed no reconnection before process replacement. Only the
  verified web listener PID 24504 was terminated. The existing ignored launcher
  started PID 27312, whose Python child PID 34424 now owns localhost:8080.
- Fresh API started both routes disconnected and exposed chassis.motion with
  idle mode, input_timeout_ms=1000 and no log_error. Authenticated chassis
  reconnection returned disabled, motion_enabled=false, last_error=none, zero
  requested vector, refresh_count=0 and no faults. Arm stayed offline as found.
- GET /assets/app.js verified the new ChassisInput and keepalive route. Page
  reload was left to the operator; no browser control/motion buttons were used.
- MediaMTX retained listener PID 15684 on 8889. No camera, ESP32, controller,
  gateway or video service restart/file deployment was issued. No Enable,
  VELOCITY, arm move or gripper command was sent by this restart procedure.
- Existing append-only stderr contains a browser connection-aborted traceback;
  its origin predates or overlaps this launch and was not independently dated.
  The fresh state/asset requests succeeded; no claim of an entirely clean
  historical stderr log is made.
- L2 restart/reconnect checks passed. Hold/release physical behavior and stopping
  distance remain untested by the agent. Source commit e2d668f is active; only
  this factual record and the scoped log addition are committed in this follow-up.
