# Diagnose chassis motion continuing after direction release

- Status: diagnosis complete; local repair implemented in the linked follow-up;
  backend replacement and attended acceptance pending
- Baseline: `58cc8d9`, `target/arm-ui-command-fixes`
- Initial audit: preserve user `.vscode/settings.json`; retain this agent's
  uncommitted arm-XYZ diagnostic plan/log record without mixing its scope.
- Request: diagnose reported continued chassis motion after a held direction.
- Risk: real motion safety incident; diagnosis limited to L0/L1 and read-only L2.

## Ownership and boundaries

Editable: this plan, factual `plan/log.md`, ignored diagnostic output.
Read-only: `src/console/`, `src/esp32/`, protocol, tests, device state and logs.
Do not Enable, send velocity/motion, deploy, reset, disconnect, restart or alter
device configuration. The operator has been asked to retain STOP/Disable.

Trace browser pointer/keyboard release, backend held-velocity lifecycle, wire
hold semantics and ESP32 deadline cleanup. Use existing logs and GET status only.
Reproduce timing/race conditions with fake clients; do not infer physical stop
from a PC event alone. Distinguish browser STOP failure, backend refresh leakage,
ESP32 deadline failure and motor/CAN latch behavior. If live status lacks the
required internal fields, report the observability gap.

Record findings and the smallest correction/test plan. Run diff/status checks.
Diagnosis alone does not authorize runtime edits, hardware writes or push.

## Findings and validation

- PC GET /api/state reported online, enabled_stopped, requested zero velocity
  and a configured 500 ms hold. This is logical state, not measured motor stop.
- The browser does not define a persistent direction-button hold-mode toggle.
  APPLY & HOLD starts an exact vector that continues until STOP; directional
  pointer/key release is intended to stop regardless of earlier exact-vector use.
- Confirmed PC race: start_chassis_motion releases the I/O lock after VELOCITY
  but before assigning _held_velocity. Concurrent STOP can clear that value and
  finish, after which the old start writes it back. The worker then keeps sending
  VELOCITY even though STOP completed. A second race lets motion_once send a
  copied stale velocity after STOP; this alone is bounded by device hold expiry.
- Ignored tmp/diagnose_chassis_hold_races.py reproduced both interleavings with
  the actual WebConsoleRuntime and fake clients. First case: four subsequent
  refresh ticks all sent velocity after completed STOP and hold remained set.
  Second case: one stale velocity followed STOP while hold remained cleared.
  No network or hardware client was instantiated in these reproductions.
- ESP32 source clears its deadline/active sequence on STOP, Disable and expiry.
  Its server uses a 50 ms socket timeout and polls safety on idle reads. Each
  newly received VELOCITY renews the deadline, so continuous PC refresh prevents
  the 500 ms expiry even when the operator is no longer holding a direction.
- Browser release delivery is not acknowledged as ongoing operator presence.
  A lost release/STOP can likewise leave backend refresh running indefinitely.
  The documentation claim that device hold expiry covers an undelivered browser
  STOP is incorrect while the PC worker is alive and continues refreshing.
- Logs contain velocity then STOP DONE (for example 09:49:35.222 / .428), but
  background refresh uses journal=False. They omit browser release events,
  hold state and wire sequence, so the exact historical trigger cannot be proven
  and no physical motor feedback or deployment readback is claimed this turn.
- L1 existing suites: 15 ESP32 motion-service tests and 13 web-console tests
  passed. Their existing hold test is sequential and misses these interleavings.
  Both offline reproductions confirmed defects. Diff/status checks passed.

## Proposed correction, not implemented

Make STOP invalidate in-flight starts and refreshes, not only clear a variable;
serialize motion lifecycle with transport dispatch and use command generations
to reject stale work. Separate explicit exact-vector hold from momentary input
semantics, with internal browser-release/presence handling and no extra operator
acquire/lease/enable steps. Record input source, generation, release/STOP reason,
hold state and renewal diagnostics without flooding the operator journal.

Add deterministic start/STOP and refresh/STOP races plus browser press/release,
exact-hold-to-direction, late replies and lost-release coverage. Validate locally
before any service replacement; attended physical release acceptance is not run.
Runtime/device sources remain unchanged. No restart, motion or push performed.

Follow-up: [hold/release repair](../2026-09-03-chassis-hold-release-fix/plan.md)
implements the PC correction and offline regressions. The findings above record
the pre-fix source and are not claims about post-fix behavior or hardware acceptance.
