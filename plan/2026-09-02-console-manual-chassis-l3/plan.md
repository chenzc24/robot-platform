# Hardware Manual Chassis Debug Panel

- Status: `completed`
- Responsible: `agent`
- Highest validation level: `L1` for implementation; a separate immediate L3
  gate is required before any hardware motion test.

## Objective

Extend the existing control-console Hardware mode with one explicit manual
chassis debug session. The panel must expose the already deployed RCP/TCP v2
control lifecycle without automatic connection, ownership, enable, or motion.
When enabled by ignored local configuration, it must provide acquire, bounded
heartbeat, enable, hold-to-run velocity, stop, disable, release, status, and
fault evidence.

## Initial workspace state

The branch started clean apart from the work created by this goal. The ignored
`config/console.local.json` may contain a deliberately enabled local manual
setting; it is configuration only and is neither read into Git nor contacted by
automated validation. User-owned `.vscode/settings.json`, device backups, and
credentials remain outside this goal.

## Editable scope

- `src/console/ui/` and `src/console/README.md` for runtime session admission,
  manual heartbeat/hold orchestration, controller/view bindings, and the local
  console launch boundary
- `config/console.example.json` and local ignored console configuration only
  for secret-free manual-session options
- `tests/console/` for deterministic manual-session, default-deny, and UI
  bindings using fake clients only
- `docs/console/`, `docs/runtime/`, and `plan/` for this feature and factual
  results

## Read-only scope

- ESP32 source, deployed device files, protocol schema, MaixCam, robot arm,
  raw-resource archives, credentials, local endpoint values, and user settings

## Shared dependencies

- The deployed ESP32 RCP/TCP v2 L3 service and its device-side authentication,
  lease, hold-expiry, disable, and CAN safeguards.
- The stable direct computer-to-ESP32 runtime boundary in `docs/overall-plan.md`.
- PySide6 queued UI signals and the existing non-retrying chassis TCP client.

## Safety and behavior requirements

- Default configuration remains hardware motion denied.
- No connection, lease, enable, or velocity occurs automatically.
- Motion requires all of: enabled local manual setting, online/authenticated
  session, acquired lease, confirmed device motion permission, enabled chassis,
  and the operator holding a direction control.
- The panel sends a bounded velocity at a fixed cadence while held and enqueues
  stop on release. It renews the lease only during an armed manual session.
- Disconnect, session fault, application close, or failed heartbeat clears the
  UI manual state; ESP32 retains its independent hold/lease stop behavior.
- This code goal does not run a real-device motion test. Later hardware use
  requires the immediate L3 safety gate.

## Validation

- L1: local unit/UI tests and offscreen UI smoke test with no endpoint access.
- Verify default configuration rejects all motion commands and the manual
  configuration admits only the named chassis operations.
- Verify cadence stops on release, heartbeat stops on disconnect/fault, no
  command is automatically retried, and hardware buttons match state.
- Run `git diff --check`, inspect staged scope, record facts, commit, and push.

## Actual results

- Added an explicit, local-only `manual_chassis` configuration block whose
  committed default is disabled. It is required before the runtime admits the
  seven state-changing chassis commands.
- Added Hardware-mode controls for the existing RCP/TCP v2 sequence:
  acquire, heartbeat, enable, bounded velocity, stop, disable, and release.
  The application remains disconnected and idle until the operator invokes
  Connect, and it never reconnects or retries an uncertain action.
- Added fixed-cadence manual heartbeats and hold-to-run velocity refreshes.
  Pending velocity/heartbeat requests coalesce; stop-like requests discard
  stale periodic output and run next. Releasing a direction, clearing manual
  unlock, disconnecting, and a session failure clear the local hold state.
- L1 validation passed: console tests `36 passed`; ESP32 `56 passed`;
  protocol `28 passed, 6 subtests passed`; MaixCam `44 passed`; robot-arm
  `9 passed`; development tooling `23 passed`. The offscreen console smoke
  test and Python compilation passed without endpoint access. `git diff
  --check` passed.
- No device, socket, video stream, credential, or motion command was accessed
  in this goal. A real panel test was intentionally not run because it needs a
  new immediate L3 safety gate.

## Outstanding matters

- The panel has no motor-driver acknowledgement, wheel feedback, CAN bus-off
  recovery, or arm interlock evidence. It is an attended L3 debug surface, not
  a production autonomy or L4 coordination release.

## Commit intent

```text
feat: add manual chassis debug session to console
```
