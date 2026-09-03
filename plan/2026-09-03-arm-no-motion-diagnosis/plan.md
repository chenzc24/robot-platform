# Diagnose successful UI replies without physical arm movement

- Status: diagnosis complete; runtime repair not requested or performed
- Baseline: `4f9e383`, `target/arm-timeouts-manual-ui`
- Initial audit: only user-owned `.vscode/settings.json` is dirty; leave untouched.
- Request: diagnose the operator-reported lack of arm movement despite DONE.
- Risk: L1 static/offline reproduction and L2 read-only status/log inspection.

## Ownership and boundaries

Editable: this plan, factual `plan/log.md` entry, optional diagnostic evidence
under ignored `tmp/` or logs.
Read-only: console, gateway and controller runtime, generated deployment
package, raw resources, protocol, existing logs, device source/configuration.
Shared dependencies: RPA2 framing/lifecycle, controller Python API adapters,
the operator's already-running UI and single-owner UART gateway.

Do not restart services, modify/deploy runtime code, seize device connections,
Enable, send movement/gripper commands, or change controller settings. Use the
running PC status API and read-only SSH process/log/file checks. Local fake
API reproductions may exercise code without network or physical output.

## Validation and handoff

Trace existing UI events to dispatch, downstream parsing/execution and result
mapping. Compare deployed MaixCam code hashes with repository source and inspect
the operator-imported controller package locally. Distinguish proven software
faults from vendor/controller behavior that has not been observed directly.
Record findings with line references and the smallest next diagnostic/fix.
Run `git diff --check` and status. No runtime edits or remote Git writes are
authorized by this diagnosis-only request; leave local evidence for review.

## Findings

1. `WebConsoleRuntime._arm_payload` converts acceleration and speed to floats
   (line 511) and gripper width to float (line 504). MaixCam preserves their
   string representation in RPA2: `accel_pct=20.0;speed_pct=20.0` and
   `width_mm=28.0`. The controller `_integer` accepts only digit strings, so
   these requests fail with `invalid_acceleration` or `invalid_gripper` before
   any motion API is invoked. Joint/pose coordinates may remain floating point;
   the mismatch concerns the protocol's integer fields.
2. The gateway correctly translates controller ERROR into FAULT. The PC
   `dispatch_arm` only checks REJECTED, not FAULT; `_arm_request` then records
   DONE/completed whenever no Python exception was raised. Thus the journal's
   apparent success is generated on the PC and is not a controller DONE.
3. Status mapping stores controller `last_error`, but does not surface a
   non-none value in the fault list. This further hides the rejection.

## Evidence and validation

- Existing UI journal: repeated jog_joint DONE through 09:11:44.035. Read-only
  GET `/api/state` instead reported arm ready/YOLO, `invalid_acceleration`,
  valid unchanged joints [-90, 0, -140, -40, 0, 0], sample 268, and empty faults.
- Read-only SSH SHA256 checks of deployed gateway and command service matched
  repository sources exactly. The local operator-import package main.py still
  hashes to `700dc58d9cb2dcf97762f59b8a3c346d7fd2f4c140b9378c06323e55692dc8b4`.
  No direct controller filesystem readback was performed this turn.
- Ignored `tmp/diagnose_arm_no_motion.py` uses the production web runtime,
  client, gateway, codecs and arm service with a recording-only fake vendor API.
  It opens no network/socket and exercises no physical API.
- All five cases reproduced: joint jog, XYZ jog, absolute joint, absolute pose,
  gripper. Each produced controller ERROR, zero fake motion API calls, an
  incorrect UI DONE, and an empty fault list. A control case using integer
  acceleration/speed bypassed the web coercion and reached the fake API once.
  All six assertions/cases passed. This does not validate physical movement.
- No browser clicks, Enable, motion/gripper request, service restart, runtime
  edit or deployment occurred. Device/PC services are left running.

## Smallest repair proposal

Preserve and validate integer protocol fields in PC normalization; handle
FAULT/REJECTED/UNKNOWN and malformed terminal responses explicitly; preserve
controller error details in events/faults instead of manufacturing DONE. Add
cross-layer regressions covering the five requests and error mapping. The
identified mismatch can be repaired on PC without rebuilding/reimporting the
arm project or changing device limits. A later operator test remains necessary
to establish physical execution after this rejection is fixed.

The subsequent user-authorized PC repair is recorded separately in
[the repair plan](../2026-09-03-arm-ui-command-fixes/plan.md).
