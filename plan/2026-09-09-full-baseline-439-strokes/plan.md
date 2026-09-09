# Full 439-stroke Baseline drawing run

- Status: complete
- Responsible: joint
- Highest validation level: L4

## Objective

Execute the repository's reviewed 439-stroke / 3,903-point sample once through
the unified `baseline` coordinator on the deployed ESP32, MaixCam arm gateway
and robot-arm controller. Use the 700 x 200 mm drawing geometry, coworker-tested
User-Y window `[-200,180]`, and the now physically observed `+vx` vehicle-forward
direction. Do not use AprilTag or automatically fall back to another strategy.

## Initial audit and ownership

- `main` and `origin/main` are synchronized at `5a59eea` after recording the
  single positive-vx direction test.
- `.vscode/settings.json` is an unrelated user change. It is read-only,
  excluded from this goal and will not be staged.
- The ignored `config/drawing.local.json` and
  `config/drawing-control.local.json` are user-approved site configuration.
  They currently select Baseline, 700 x 200 mm, initial JSON offset 0 mm,
  rail-to-JSON scale -1, 50 mm/s relocation speed, 250 ms hold, 300 mm maximum
  hop and 2,000 ms settling, but both still carry the deliberate default-deny
  `production_ready=false` gate.
- The previous one-device L3 result establishes the sign of `+vx`, but does not
  metrically validate open-loop speed-by-time travel, wheel slip, acceleration
  or stopping distance.

## Editable scope

- this plan and append-only `plan/log.md`
- `docs/console/drawing-control-modes.md`, limited to clarifying that a proven
  read-only preflight failure may be followed by a new explicitly authorized
  run; the no-automatic-retry rule remains for state-changing/unknown outcomes
- `src/console/maixcam_arm_client.py` and its focused client test, limited to
  encoding integral gripper widths as the integer representation required by
  the deployed arm protocol
- `src/console/drawing/config.py`, `planner.py`, `simulator.py` and
  `image_input.py`; the drawing configuration templates/local file; focused
  drawing tests; and the drawing-coordinate documentation, limited to replacing
  the implicit Home-zero Y/Z mapping with explicit Home-relative canvas vectors
  while preserving every current planned translation exactly
- ignored `config/drawing.local.json` and
  `config/drawing-control.local.json`, limited to changing their reviewed
  `production_ready` gates for this run
- one new ignored durable execution log under `logs/`

## Read-only scope and dependencies

- `dataset/dobot-generation-1.json`
- `app/`, `src/`, `protocol/`, committed templates and deployed device source
- ESP32 and MaixCam filesystems, robot-arm project and controller parameters
- `.vscode/settings.json`

The run depends on the already deployed `d2469eb` payload, current local console
credentials/endpoints, the active robot-arm service, the ESP32 v3 runtime and
the fixed physical board/User0/start-position relationship represented by the
configured zero initial offset.

## Planned procedure

1. Parse both local configurations and the sample; run the unified runner in
   no-device dry-run mode and capture the exact job SHA-256.
2. Rehearse every planner barrier offline to enumerate arm windows, commanded
   JSON offsets, chassis distances/directions and total open-loop travel.
3. Perform fresh L2-only status checks for ESP32, MaixCam video/gateway and arm;
   require the chassis disabled/idle and arm ready with valid feedback.
4. Explain the exact expected coordinated sequence, stop conditions and failure
   response, then obtain a new explicit on-site L4 safety confirmation for this
   full run.
5. Change only the two reviewed local `production_ready` gates to true, run the
   exact job once with a new log, and do not retry an unknown or failed action.
6. Require final STOP/DISABLE, inspect the durable log and final device states,
   record only observed facts, validate the scoped diff, commit and push the
   plan/log record.

## Safety and failure behavior

- The operator must be present with the physical emergency stop operable; the
  full chassis/arm envelope and pen/board area must be clear; the chassis must
  be restrained or inside the agreed safe travel area; and the reviewed arm
  pose, workspace, speeds and load must still be valid.
- Baseline relocation is open-loop. Each barrier returns the pen, sends the arm
  to its configured safe Home, commands one bounded chassis movement, sends
  STOP, requires `enabled_stopped`, settles for 2 seconds, then resumes from the
  exact checkpoint using commanded rather than measured offset.
- Any unexpected physical direction, contact, instability or unsafe approach
  requires the on-site physical emergency stop. A rejected, faulted, timed-out,
  disconnected or unknown command stops later commands; no automatic retry,
  AprilTag correction, fallback or checkpoint recovery is permitted.

## Validation and commit intent

- L1: configuration parsing, unified dry-run, deterministic full-window
  rehearsal and `git diff --check`
- L2: fresh no-motion endpoint and state checks
- L4: one explicitly confirmed attended full drawing run only
- stage only this plan and `plan/log.md`; never stage local configuration,
  runtime logs or `.vscode/settings.json`; commit and push factual results

## Actual results

- The first invocation was rejected before device access because the chassis
  credential environment variable was absent.
- A second invocation authenticated the chassis and reached Baseline window 1,
  then the arm's read-only preflight `PING` returned `response_timeout`. No
  `window_ready` or `step_start` event exists, so no arm motion command was
  submitted. The shutdown path completed and a fresh authenticated chassis
  status confirmed `ready/disabled`, zero hold and no error.
- A subsequent read-only arm `PING` completed successfully. The operator then
  explicitly authorized a new full 439-stroke run and requested that the
  preflight/manual-restart distinction be documented.
- That run passed arm preflight and completed its first `arm.move_joint`, placing
  the arm at the configured yellow P1 rack pose. Its next command was explicitly
  rejected as `invalid_gripper`; zero drawing strokes and no chassis relocation
  occurred. Read-only status confirmed the arm ready and stationary at P1 with
  no active sequence. Static inspection found that the drawing configuration
  intentionally accepts millimetre numbers as floats, while the PC client sent
  `60.0` and the deployed controller requires integer gripper text such as `60`.
- After integer serialization was fixed and tested, an explicitly authorized
  new run again completed the P1 joint move. Its gripper-open request then
  exceeded the client's 2,000 ms motion TTL and terminated as
  `outcome_unknown`. No drawing stroke or chassis relocation occurred. Current
  read-only status reports the arm ready at P1 with no active sequence and no
  error, and the chassis `ready/disabled` with zero hold and no error, but the
  protocol cannot report measured gripper terminal position. The production
  gates were returned to false pending operator observation.
- After the operator confirmed the arm stopped and the gripper state was
  acceptable, the next full invocation passed pen selection and began drawing.
  It completed 35 arm commands, then `outcome_unknown` occurred on point 19 of
  yellow stroke `stroke_0281946cfebe`; the operator reported physical contact
  and began clearing the abnormal state. No planner barrier or chassis
  relocation had occurred. The operator requested faster drawing, so the local
  draw-segment speed was raised from 12% to 20% while travel remained 50%; the
  production gates remain false until recovery is explicitly confirmed.
- The operator reported the physical abnormal state cleared and explicitly
  reconfirmed the attended site safe for a new full run at the adjusted speed.
- That run completed three yellow strokes but stopped with `outcome_unknown`
  during the pen-up 50% travel anchor for yellow stroke `stroke_0fd6f99359fc`.
  No chassis relocation occurred. The operator reported severe gripper jitter;
  no further motion will be sent while that condition exists. At the operator's
  request, the local draw-segment speed was changed from 20% to 35%, while the
  production gates were returned to false. The prior anchor failure used the
  unchanged 50% travel speed, so this draw-speed change does not claim to fix
  the contact or gripper condition.
- The operator subsequently confirmed that the arm had stopped and the gripper
  state was acceptable, and explicitly authorized continuing the 439-stroke
  task with the corrected client.
- The controller later reported no inverse solution for the relative vector
  `[0,-188.0634,-15.444933333,0,0,0]`, which exactly maps to the first point of
  yellow stroke `stroke_0fd6f99359fc` under the existing formula. The operator
  requested a no-behavior-change coordinate refactor: Home becomes the explicit
  PC-side local reference and every canvas target is represented as a vector
  from Home. No hardware command is part of this refactor; actual calibrated
  Home and board values remain a later parameter-tightening task.
- Replaced the active local/template scalar geometry with explicit Home-relative
  top-left, U, V, rail-offset and pen-down vectors. The loader accepts legacy
  scalar files only as a lossless compatibility input; the planner consumes only
  the Home-relative vectors. Current local values preserve the former
  translations exactly and keep `production_ready=false`.
- L1 passed 30 focused drawing/configuration/simulator/CLI tests and 15 focused
  arm-client/executor tests, Python compilation, `git diff --check`, three
  old-vs-new full-job equivalence checks at offsets 0, +137.25 and -80.5 mm,
  and a complete no-device 439-stroke / 3,903-point simulation (six windows,
  five relocations, 1,215.8966 mm rail travel). The repository's flat test-root
  discovery command found zero tests because tests are organized in nested
  non-package directories; it is not claimed as a suite pass.
- No device connection, service operation, configuration write, arm command,
  chassis command or physical motion occurred during this refactor. The
  unrelated web-console work and `.vscode/settings.json` remain unstaged.
