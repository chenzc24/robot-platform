# Tighten the Home-relative Y drawing window

- Status: complete (L1 implementation and simulation only; hardware release pending)
- Responsible: joint
- Highest validation level: L4

## Objective

Keep the 700 x 200 mm logical and physical canvas unchanged while reducing the
local Home-relative drawing Y window from `[-200,180]` to `[-180,160]` mm. The
specific previously rejected anchor at Y=-188.0634 must now be caught by the
planner before an arm command is formed.

Extend the same production-path goal with an offline-only motion-throughput
redesign: preserve the Home-relative coordinate reference and all safety
barriers, remove the redundant Home return between ordinary completed strokes,
and introduce a bounded, explicitly acknowledged arm-side stroke queue so
continuous draw segments can reach the controller without a PC-side terminal
wait between every point. A Home return remains mandatory before chassis
relocation, pen-rack actions, task completion and terminal failures.

## Initial audit and ownership

- `main` is synchronized with `origin/main`; the only unrelated dirty path is
  `.vscode/settings.json`, which adds local MicroPython UI buttons and remains
  read-only.
- `plan/log.md` is clean at this audit. It will be updated only after the
  implementation and validation facts are known.
- `config/drawing.local.json` is ignored, user-approved site configuration;
  its production gate is false and will remain false.

## Editable scope

- this plan only
- `src/console/drawing/`, `src/console/maixcam_arm_client.py`,
  `src/maixcam/`, `src/robot_arm/runtime/`, and the directly related tests
- the affected arm/motion protocol and runtime/deployment documentation
- `plan/log.md` only for the final factual record, if it remains clean
- ignored `config/drawing.local.json`, limited to the two Home-relative Y limits
- ignored `config/drawing.local.json` and `config/drawing-control.local.json`,
  limited to temporarily arming their existing production gates for one
  explicitly confirmed Baseline run
- one new ignored durable execution log under `logs/`

## Read-only scope and dependencies

- drawing JSON and device filesystems
- `ESP32/`, `Camera/`, `Robot Arm_Claws/` raw-resource archives
- all unrelated committed templates and `.vscode/settings.json`

Shared dependencies are the PC-to-MaixCam lifecycle envelope, MaixCam-to-arm
motion-link transport, controller-side RPA2 primitive semantics, existing
Home-relative geometry, the checkpoint/relocation contract, and the existing
non-retry rule for uncertain state-changing commands.

## Validation

- protocol and runtime unit tests for bounded queue admission, ordering,
  terminal lifecycle and error handling
- drawing planner/executor tests proving ordinary strokes lift then continue
  without an intermediate Home, while pen change, relocation and final return
  still Home
- parse the local configuration and run the unified no-device dry run
- simulate the real 439-stroke job and inspect the first barrier/checkpoint
- verify the prior Y=-188.0634 target is outside the new window
- `git diff --check` and scoped status audit

## Safety and completion

The operator explicitly reconfirmed the attended site safe for this full run:
an operator and physical emergency stop are present, the arm/chassis envelope
is clear and constrained to the agreed work area, and the reviewed Home,
workspace, speed and load profile remain in effect. This parameter only changes
PC-side planning admission; it is not an IK proof or a replacement for physical
calibration. Any failure stops later commands without automatic retry. The goal
remains uncommitted until the shared factual log can be safely coordinated.

The previously started Baseline job was deliberately interrupted at the PC on
the operator's request during a relative arm command. This is not a controller
cancel primitive: no automatic follow-up command or recovery motion will be
issued. Further work is L0/L1 only until a separately confirmed hardware run.

## Actual results

- Updated only the ignored local Home-relative Y limits to `[-180,160]` mm;
  canvas vectors, pen-down vector, JSON geometry and `production_ready=false`
  are unchanged.
- The unified real-sample dry run passed without opening a device and now stops
  its first executable window at group 0/stroke 4 rather than issuing the prior
  unsafe anchor.
- A targeted plan from yellow stroke `stroke_0fd6f99359fc` rejects its first
  anchor Y=-188.0634 before motion, returning only `arm.home` and
  `reposition.required`; the required JSON-axis offset delta range is
  `[8.0634,348.0634]` mm.
- The complete no-device simulation passed but the narrower 340 mm window
  increases the real 439-stroke sample from six windows/five relocations to
  13 windows/12 relocations, with 2,405.9764 mm total ideal rail travel and
  nine direction reversals. This is a planning tradeoff, not a physical-motion
  result.
- `git diff --check` passed. No device connection, service action or motion
  occurred. Shared `plan/log.md` remains untouched because it is dirty from the
  separate Web-console task; this plan is intentionally not committed yet.
- A user-authorized Baseline run was started after its local production gates
  were armed. It completed its first planned chassis relocation and continued
  drawing until the user requested a stop for throughput investigation. The PC
  process was interrupted while awaiting one relative-arm command; that action
  has no controller cancellation semantics, and no automated recovery command
  was issued. The local production gates were then reset to false.
- The investigation showed that explicit planner sleeps were only 1.4% of the
  observed completed-step time; PC-side terminal waits around individual
  relative segments accounted for 77.1%, and per-stroke Home motions for
  20.4%. The conclusion is based on the local execution log, not a new
  controller timing claim.
- Implemented an incompatible, bounded staged-stroke protocol across the PC,
  MaixCam, RPA2 runtime and controller source. One stage upload carries 1--8
  draw deltas, the controller accepts at most 128 per stroke, and only
  `STROKE_EXECUTE` moves: anchor, pen down, CP draw deltas and pen up execute
  in controller Python. Ordinary same-pen strokes now continue from the last
  lifted endpoint; Home remains mandatory after pen selection, before a rack
  return/reposition, at checkpoint resume and at final return.
- L1 passed: 72 focused tests, including controller runtime (11), MaixCam
  command service (9), PC arm client (12), drawing planner (13), drawing
  executor (6), localized coordinator (2), protocol, project-builder and app
  entry-point coverage. The actual 439-stroke
  input passed the unified no-device dry run and the 13-window / 12-relocation
  localized simulation. The simulator reports 442 queued-stroke transactions
  (three strokes cross a window barrier) and 607 total PC-side arm calls. No
  updated controller project, MaixCam
  gateway or PC runtime was deployed; no post-change device connection or
  motion was attempted.
- Residual risk: a complete staged stroke returns one terminal lifecycle rather
  than one lifecycle per point. Its controller timing and the 60-second
  execution TTL require a separately approved low-speed single-stroke L3
  validation before any L4 drawing. The old deployed controller project does
  not recognize this protocol and must not be used with the updated PC client.
