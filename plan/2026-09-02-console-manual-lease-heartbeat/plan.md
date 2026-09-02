# Console Manual Lease Renewal

- Status: `completed`
- Responsible: `agent`
- Highest validation level: `L1`

## Objective

Correct the manual console lease workflow after live diagnostics showed that a
5 s client lease exceeds the deployed RCP/TCP v2 maximum of 2000 ms. Keep an
explicitly acquired, non-motion lease alive until the operator enables or
releases the session.

## Initial workspace state

The live diagnostics log records two `ACQUIRE` replies with `invalid_lease`
after the local lease was set to 5000 ms. The protocol contract defines a
250–2000 ms range. No device operation is planned in this implementation goal.

## Editable scope

- `src/console/ui/controller.py` and `src/console/ui/runtime_config.py`
- `config/console.example.json`, ignored local configuration, console docs,
  `tests/console/`, this plan, and `plan/log.md`

## Read-only scope

- ESP32 source/device configuration, protocol contract, credentials, endpoints,
  MaixCam, robot arm, raw resources, and user settings.

## Safety requirements

- Use only the deployed protocol's legal 2000 ms maximum.
- Start renewal only after an operator-clicked Acquire returns a status owned
  by this console. The renewal emits `HEARTBEAT` only; it never enables or
  moves the chassis.
- Stop renewal on release, disconnect, fault, unknown session state, or lost
  ownership. The device independently expires and disables stale sessions.

## Validation

- Verify the configuration rejects leases above 2000 ms.
- Verify an owned non-motion Hardware state starts only heartbeat renewal and
  no velocity; verify a lost owner stops it.
- Run console tests, offscreen smoke, compilation, workspace validation, and
  diff-format checks without device access.

## Actual results

- Restricted local manual leases to the RCP/TCP v2 range of 250–2000 ms and
  set the committed and ignored local defaults to 2000 ms.
- After a `STATUS` frame confirms that this Hardware console owns the lease,
  the periodic worker now emits heartbeat renewals even while the chassis is
  disabled. It emits velocity only after the separate enable/unlock gate is
  satisfied. Lost ownership stops the timer and clears local manual state.
- L1 validation passed: 40 console tests, offscreen smoke test, Python
  compilation, workspace validation, and diff-format check. No device endpoint
  was accessed by this implementation goal.

## Outstanding matters

- Restart the console to load the legal lease and renewal behavior. Any enable
  or motion remains an attended L3 action requiring an immediate on-site
  safety confirmation.

## Commit intent

```text
fix: renew manual chassis lease after acquire
```
