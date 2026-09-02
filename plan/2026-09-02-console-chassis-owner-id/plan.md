# Console Chassis Lease Owner Mapping

- Status: `completed`
- Responsible: `agent`
- Highest validation level: `L1`

## Objective

Correct the Hardware console's lease-owner comparison so that it uses the
configured ESP32 client identifier rather than the simulator-only literal
`console`.

## Initial workspace state

The manual console branch is synchronized. The user supplied a screenshot with
an authenticated L2 status showing owner `console-l2`; Acquire completed, but
the console left Enable disabled. No device operation is planned in this goal.

## Editable scope

- `src/console/ui/controller.py` and `src/console/ui/views.py`
- `tests/console/`
- this plan and `plan/log.md`

## Read-only scope

- ESP32 and all device files, local configuration and credentials, protocol,
  MaixCam, robot arm, raw resources, and user settings.

## Shared dependencies

- The RCP/TCP v2 `lease_owner` status field and local chassis `client_id`.

## Validation

- Verify a fake Hardware session using `client_id=console-l2` admits Enable
  after a matching acquired lease.
- Run console tests, offscreen smoke, diff-format check, and no device access.

## Actual results

- Replaced the Hardware-mode literal lease-owner comparison with the configured
  chassis `client_id`. Simulator behavior retains its fixed `console` owner.
- The view now uses the same controller-derived owner name as the Hardware
  enablement and manual-motion checks.
- L1 validation passed: `37` console tests, offscreen console smoke test,
  Python compilation, and `git diff --check`. No device endpoint was accessed
  by this implementation goal.

## Outstanding matters

- Restart the local console to load the corrected process. A fresh attended L3
  safety confirmation is required before any enable or motion action.

## Commit intent

```text
fix: use configured chassis lease owner in console
```
