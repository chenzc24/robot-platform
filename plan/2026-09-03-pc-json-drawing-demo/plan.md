# PC JSON drawing demo

- Status: implementation and L1 validation complete; commit/push pending
- Owner: Codex, single-agent implementation
- Validation: L0/L1 only; hardware validation is deferred
- Baseline: target/chassis-hold-release-fix, tracking its origin branch

## Objective

Add app/demo.py to read normalized JSON strokes and reproduce the supplied
controller-side demo through the existing PC -> MaixCam -> arm command route.
Copy the supplied railway JSON into a root dataset directory and ignore it.
Do not connect, deploy, enable, grip, move, reset, or restart real hardware.

## Initial workspace audit

Initial status contains user-owned .vscode/settings.json, a prior XYZ diagnostic
addition in plan/log.md, and untracked XYZ diagnosis, YZ drawing review, and video
diagnosis directories dated 2026-09-03. These are identified prior-goal work,
not this implementation. All are read-only and must remain byte-identical.
Runtime/protocol sources and .gitignore are clean; app/ does not yet exist.
The shared log is excluded pending explicit coordination. A non-blocking request
asks permission to append and selectively stage only this task's log hunk.
The user subsequently authorized appending this goal's log entry. Preserve the
prior log content and stage only the new goal entry, not the prior dirty hunk.
While implementation was running, a separate recovery task committed 71eb8b0
on the original branch. Re-audit found only its scoped plan/log addition and
the unchanged prior XYZ dirty log hunk; no drawing source overlap. Preserve
that commit and base this branch on it. Other initially dirty files retain
their SHA-256 hashes. Never claim those independently performed device actions
as validation of this no-hardware goal.

## Editable scope

- app/demo.py and app/README.md.
- tests/app/test_demo.py.
- .gitignore: add root /dataset/ only.
- dataset/strokes_railway_new.json: ignored byte-for-byte input copy.
- This goal directory, including factual results if shared-log work is deferred.
- plan/log.md only after explicit coordination; never stage prior log edits.

## Read-only scope and shared dependencies

All other repository paths and all original data/raw archives remain read-only.
In particular: protocol/, src/console/, src/maixcam/, src/robot_arm/, src/esp32/,
configuration, generated device projects, previous plans and user settings.
Reuse MaixCamArmClient, runtime configuration, and current status parsing.
Use current control-envelope v1 and RPA2 primitives without contract changes.
ESP32, simulators, device code, calibration, and deployment are unaffected:
the only new runtime consumer is the PC demo. Tests use the existing gateway
and arm service with fake IO, never vendor code or sockets to hardware.

## Behavior and compatibility decisions

- Validate the entire version 1.0 normalized top-left JSON before opening IO.
- Preserve stroke order, every point, skipped short strokes, and stroke breaks.
- Keep the supplied home joints [-120, 0, -90, -90, -30, 90], User Y/Z mapping
  Y=100*u-30 and Z=100*(1-v)-30, and User X -20/+20 pen motion.
- The JSON target dimensions are 210 x 210 mm metadata, not execution settings;
  retain the requested demo's 100 x 100 mm mapping by default and disclose it.
- Explicit configuration/CLI overrides for geometry, frames, speed, and endpoint;
  do not scatter hardware addresses or silently change calibration.
- Keep draw speed 15%; choose explicit travel speed/acceleration 5% because
  the original unspecified controller defaults are unknown.
- The existing route disables blending. Do not add cp=100 support or claim
  identical continuous timing/corner rounding. Wait for each DONE; no retries.
- Default is a no-network preview. Real execution requires an explicit flag
  and current attended safety confirmation; no real execution in this goal.
- A failure/UNKNOWN/interruption aborts all remaining commands. Do not blindly
  lift the pen or home in cleanup, and do not claim socket close is an e-stop.
- DONE means the controller API returned, not verified physical end position.

## Risks and validation

Motion-capable client, but all actual work stays L0/L1. The fixed joint posture,
paper plane, pen direction, User/Tool identity, grip width, reachability, and
singularity clearance are unverified for a current physical setup. L3 requires
an on-site operator, physical emergency stop, confirmed stopped/restrained
chassis, clear area, safe pose/workspace, low speed/load and explained failure
response. No native safety limits or hardware configuration may be changed.

Planned checks: JSON parsing/finite bounds/order, exact demo mapping, no loss of
endpoints, ordering/delays, zero-network default, failure/UNKNOWN abort without
retries or cleanup motion, status readiness, fake full protocol round trip,
existing arm/client/protocol tests, CLI preview on the supplied data, copy hash
and git ignore verification, git diff --check and final status/ownership audit.

## Actual results

- Added app/demo.py and its usage/compatibility notes, without device or shared
  protocol modifications. Runtime dependencies remain the existing PC client.
- Copied dataset/strokes_railway_new.json byte-for-byte; source and destination
  SHA-256: 0260260962ff9e86e86f7b54d9232845082b4ae6523301b600a0b61615491902.
  Root /dataset/ ignore rule verified; the input is not staged or committed.
- Supplied input: 4 strokes, point counts [149, 58, 37, 25], 269 total points.
  Default plan: 282 arm commands plus 8 local pause steps, keeping all points.
- New tests: 16/16 passed, including real PC/gateway/RPA2/native-adapter round
  trips with fake device IO, geometry/frame/speed checks, short/invalid input,
  status rejection, no-network preview, failure/UNKNOWN/interruption abort and
  connection cleanup without motion.
- Existing regressions: PC client 7/7, arm runtime 8/8, gateway command service
  7/7, protocol 28/28. Total: 66 tests passed.
- Entire supplied dataset also passed the fake full route: 282 recorded native
  API calls, no hardware/network IO. Preview passed from repository root and
  another working directory with the default repository-relative data path.
- git diff --check passed; dataset ignore and input hashes verified. Initial
  user settings and three unrelated diagnosis/review directories are unchanged.
- L2/L3/L4 not run: no real connection, gripper action, arm/chassis motion,
  deployment or service change was authorized/performed by this goal.
- Residual limits: current physical setup and pen clearance are unverified;
  original cp=100 continuous blending is unsupported by the existing route;
  DONE does not establish physical terminal position. These are documented,
  not hidden by the offline test results.

## Commit intent

User approved the log append. Use target/pc-json-drawing-demo and commit only
the declared tracked task files plus this goal's new log hunk:
`feat(app): add PC JSON stroke drawing demo`.
Stage the new log hunk independently from the prior uncommitted XYZ diagnosis.
Push this goal branch; do not merge the existing branch or main. PR target is
target/chassis-hold-release-fix so review contains only this goal's change.
