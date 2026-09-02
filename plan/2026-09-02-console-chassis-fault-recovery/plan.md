# Console Chassis Fault Recovery

- Status: `completed`
- Responsible: `agent`
- Highest validation level: `L1`

## Objective

Clear stale console-side ESP32 faults after a later authoritative healthy
`STATE` response, so a recovered session is not permanently blocked by an
earlier rejected duplicate command.

## Initial workspace state

The live text log shows a first duplicate Enable rejected as
`invalid_chassis_state`, followed by fresh connect/acquire/enable success and
manual unlock. The stale fault remains in the UI and blocks the direction pad.
No device operation is planned in this implementation goal.

## Editable scope

- `src/console/ui/controller.py`, `tests/console/`, this plan, and `plan/log.md`

## Read-only scope

- ESP32 device/source/configuration, protocol, local settings/credentials,
  MaixCam, robot arm, raw resources, and endpoints.

## Safety requirements

- Clear an ESP32 fault only after a fully parsed `STATE` reports service
  `ready` and `last_error=none`.
- Do not clear device-reported faults, unknown outcomes, or any fault without
  such positive status evidence.
- Do not connect or send any device command during validation.

## Validation

- Verify a stale ESP32 fault clears after a valid clean state, while a
  non-ready/device-error state retains it.
- Run console tests, smoke test, compilation, and diff-format checks.

## Actual results

- A parsed clean ESP32 `STATE` now clears only ordinary fault-severity records
  sourced from ESP32. Unknown outcomes and faults from other sources remain
  visible and continue to require inspection.
- L1 validation passed: 41 console tests, offscreen smoke test, Python
  compilation, and diff-format check. No device endpoint was accessed by this
  implementation goal.

## Outstanding matters

- Restart the console to clear the stale UI fault after the next healthy status
  refresh. Any enable or motion remains an attended L3 action requiring an
  immediate on-site safety confirmation.

## Commit intent

```text
fix: clear recovered chassis faults in console
```
