# ESP32 positive-vx direction test

- Status: complete
- Responsible: joint
- Highest validation level: L3

## Objective

Run exactly one attended chassis direction test at `+vx=50 mm/s` for 200 ms,
verify hold-expiry stop and final disable, and record the operator-observed
physical direction. Do not test the arm or run a drawing task.

## Initial audit and ownership

- `main` is synchronized with `origin/main` at `7022de5`.
- `.vscode/settings.json` is an unrelated user change. It is read-only,
  excluded from this goal and will not be staged.
- ESP32 d2469eb payload deployment and readback passed immediately before this
  test; authenticated status was `ready/disabled`, motion permitted, zero hold
  and no error. COM7 recovery remains connected.

## Editable scope

- this plan and append-only `plan/log.md`
- no device file or configuration changes

## Safety gate

The operator explicitly confirmed for this test that a person can operate the
physical emergency stop, the area is clear, the chassis is raised/restrained or
inside the agreed safe area, and the robot arm is in a safe stationary pose.
The explained motion is one `+vx=50 mm/s` command held for 200 ms, followed by
local hold-expiry stop, verification of `enabled_stopped`, then DISABLE. Any
unexpected direction or motion requires the physical emergency stop; no
automatic retry is permitted.

## Validation

- preflight authenticated `ready/disabled` status
- one fixed `tools/esp32/l3_chassis_test.py` execution
- require reported hold-expiry stop and final authenticated disabled status
- obtain the operator's physical direction observation before concluding the sign
  calibrated
- `git diff --check` and scoped status audit

## Commit intent

Commit and push the factual record after the operator reports the observed
direction.

## Actual results

- Preflight passed as authenticated `ready/disabled`, motion permitted and no
  error.
- Executed exactly one fixed `+vx=50 mm/s`, 200 ms request. The ESP32 reported
  `velocity_hold_expired` and `enabled_stopped`; the tool then disabled the
  chassis. Final independent status was `ready/disabled`, zero hold and no error.
- The on-site operator reported that the single physical test succeeded. This
  establishes `+vx` as the intended vehicle-forward direction for the current
  wiring and deployment; no retry or opposite-direction test was performed.
- The unrelated `.vscode/settings.json` user change remained untouched and was
  excluded from this goal.
