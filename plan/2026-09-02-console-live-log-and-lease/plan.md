# Console Live Text Log and Usable Manual Lease

- Status: `completed`
- Responsible: `agent`
- Highest validation level: `L1`

## Objective

Provide a safe local text event/fault log for live console diagnosis and make
the manual session lease long enough for an operator to complete Acquire then
Enable before its first heartbeat.

## Initial workspace state

The user supplied a real-panel screenshot showing `ACQUIRE` completed, then
`ENABLE` was rejected with `control_not_owned`. The existing manual setting
requests a 1000 ms lease and the post-acquire status refresh leaves too little
time for a human to act. No device operation is planned in this goal.

## Editable scope

- `src/console/ui/controller.py` and `src/console/ui/main.py`
- `config/console.example.json`, ignored local console configuration, and
  `src/console/README.md`
- `tests/console/`, `docs/console/`, this plan, and `plan/log.md`

## Read-only scope

- ESP32 source/device configuration, credentials, protocol, MaixCam, robot
  arm, raw resources, user settings, and actual device endpoints.

## Safety requirements

- The text log contains timestamps, target, command, lifecycle, result, and
  fault code only; it never writes credentials, host addresses, raw payloads,
  or command parameters.
- Startup, logging, and test validation do not create a network session.
- The first manual heartbeat still starts only after explicit session-scoped
  unlock; the longer lease does not auto-enable or auto-move the chassis.

## Validation

- Verify a temporary log receives redacted event and fault records.
- Verify the 5 s lease flows into Acquire and heartbeat payloads.
- Run console tests, offscreen smoke, compilation, workspace validation, and
  diff-format checks without device access.

## Actual results

- The committed manual template and ignored local configuration now request a
  5000 ms lease. Manual heartbeats retain the same 250 ms cadence but still do
  not start until explicit manual unlock.
- Added a local `--event-log` console option, defaulting to the ignored
  `logs/console/latest-events.log`. Each process starts a fresh log and records
  sanitized event/fault fields only. A log failure never changes console or
  hardware behavior.
- L1 validation passed: 38 console tests, offscreen smoke test, Python
  compilation, workspace validation, and diff-format check. No device endpoint
  was accessed by this implementation goal.

## Outstanding matters

- Restart the console to load the longer local lease and text logger. Any
  subsequent enable or movement remains an attended L3 action requiring an
  immediate on-site safety confirmation.

## Commit intent

```text
feat: add console live diagnostics log
```
