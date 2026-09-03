# Attended PC JSON drawing hardware test

- Status: command-path L3 run complete; operator confirms drawing completeness
- Baseline: 832d238, target/pc-json-drawing-demo
- Highest intended validation: L3, one arm only; no chassis motion or L4 task

## Objective and authorization

Run the reviewed app/demo.py once against the currently connected arm using
dataset/strokes_railway_new.json, under the user's current on-site supervision.
The user explicitly requested the hardware test and confirmed a safe environment
and physical emergency-stop control. A follow-up asks explicit confirmation of
the current chassis stop/restraint, home pose, pen/load, frames, and parameters.
Do not send motion until the complete current-test safety gate is confirmed.
The user replied "safe" to the explicit follow-up listing all current motion
parameters, stopped/restrained chassis, pose/pen/load checks, continuous
attendance, and physical e-stop response. Current-test authorization is complete;
hardware readiness and single-client ownership still must pass before execution.

## Workspace audit and ownership

Initial branch is synchronized. .vscode/settings.json is the known user editor
change. The only dirty plan/log.md hunk is the previous XYZ diagnosis. The
untracked XYZ diagnosis, YZ drawing review and video diagnosis directories are
known prior work. They are all read-only and must not be staged or modified.
App/runtime/protocol sources and dataset are unchanged from reviewed inputs.
The user authorized appending drawing-task logs in the immediately preceding
implementation turn; append only this follow-up's facts and stage only its hunk.

## Editable and read-only scope

Editable: this new plan directory and a new section appended to plan/log.md.
Read-only: app/, dataset/, protocol/, src/, configuration, device files,
generated projects, other plans, user settings, and all raw-resource archives.
No code/configuration change, deployment, upload, restart, reset, alarm clear,
new taught points, calibration update, safety-limit update or manual jog.

## Shared dependencies and hardware scope

Existing MaixCamArmClient, local console configuration and status APIs;
control-envelope v1 and RPA2; currently deployed MaixCam arm gateway and Dobot
YOLO project. Read existing UI snapshot first to avoid a competing arm session.
If the console owns an idle, healthy arm, temporarily close only that arm client
via its documented disconnect API before the standalone demo takes ownership.
Leave video/backend/ESP32 services and chassis connection intact. Never open
a competing UART or bypass the MaixCam runtime route with LAN2 or raw commands.

## Fixed test and safety gate

Input SHA-256: 0260260962ff9e86e86f7b54d9232845082b4ae6523301b600a0b61615491902.
4 strokes / 269 points / 282 arm commands plus 8 pauses; no filtering or resume.
Home joints [-120,0,-90,-90,-30,90] per stroke, User/Tool 0/0, Y=100*u-30,
Z=100*(1-v)-30, User X -20/+20 mm pen-down/up, gripper width 1 mm once.
Draw 15%, travel 5%, acceleration 5%; no blending. Do not increase these values.
Verify current arm ready/idle/YOLO, valid fresh feedback, no current error, and
confirmed stopped chassis. The operator confirms clear area, physical e-stop,
chassis restraint/safe area, safe pose/workspace/load/pen, and continuous presence.

The agent may enter the demo's DRAW prompt only as execution of that explicit
current operator authorization, not as a substitute for it. Explain startup
gripper and repeated joint moves before sending the confirmation. Keep the
foreground process observable; no detached/unattended motion.

Stop on fault, rejection, unknown response, timeout, interruption, unexpected
physical behavior or loss of supervision. No retries, replay, automatic recovery
pen lift/home, reset or clearing alarms. Ctrl+C/socket close cannot stop an
in-flight native move; the on-site person uses the physical e-stop if needed.
DONE only proves API return; require the observer's physical result before
claiming a completed drawing. Do not return the arm with an extra home command.

## Validation and recovery

Recheck local demo preview/tests and dataset hash; obtain non-motion status and
record actual feedback/state before the test. Execute at most one sequence.
After known successful completion, query final state without motion and restore
the console's previously idle arm status session if appropriate. After unknown
motion, retain stopped command flow and request operator state before recovery.
Preserve physical safeguards and leave hardware recovery to a separately
confirmed action; there are no device writes requiring a filesystem rollback.

Always run git diff --check and git status --short --branch. Record commands
actually issued and their lifecycle separately from observed physical motion.
Commit/push only this plan and the added log section on the existing drawing
review branch; do not merge the branch or include earlier dirty work.

## Actual results

- Local preview and 16 demo regression tests passed again; input SHA-256 matches.
- Current-test physical safety/parameter confirmation received from the operator.
- Non-motion console status refresh passed through existing sessions: chassis
  enabled_stopped, idle, zero requested velocity, last_error=none, health age 0;
  arm ready/idle/YOLO/motion permitted, last_error=none, valid sample 303, age 0,
  User/Tool 0/0. Historical acknowledged timeout faults were not cleared.
- Initial measured joints: [-201.971893,-18.8151436,-114.792999,-57.9355545,
  -131.156525,104.260567]. Initial pose: [-179.461923,110.750871,124.316473,
  -112.211624,-66.5113946,130.296206]. These differ from the commanded drawing
  home; the approved demo begins with its fixed home joint move after gripper.
- Motion not yet sent; next release only the idle console arm session and run
  the unchanged demo under the confirmed current-test supervision.
- Released only the console arm session through its API; chassis stayed
  enabled_stopped. Started the unchanged foreground demo, verified printed
  parameters and entered DRAW under the explicit operator authorization.
- The very first non-motion PING returned REJECTED/request_in_flight and the
  demo exited before status/gripper/home/drawing. No state-changing command
  was issued by this attempt. The wrapper reported process exit code 1.
- Announced the pre-motion failure immediately. Continue read-only/non-motion
  diagnosis of the shared gateway pending request; no motion retry, deployment,
  restart or alarm clear. Distinguish a stale query from any unknown action
  before deciding whether current readiness can be established safely.
- Local source inspection/in-memory reproduction shows that the shared gateway
  can retain a pending STATUS across client close; a new PING is then rejected
  before ordinary UART/expiry polling clears it. This is a supported explanation,
  not proof of the exact live pending frame (gateway per-command logs unavailable).
- With the console still offline, opened one non-motion client, allowed six
  seconds for ordinary gateway polling, then received PING DONE and STATUS DONE.
  Arm ready/idle/YOLO, active_sequence=0, valid sample 315, last_error=none;
  measured joints/pose match the initial values. Closed after query completion.
  No reset/restart/config write/motion or state-changing retry was used.
- Current readiness is restored; restart the unchanged foreground demo under
  the same current-test authorization. The first launch sent only a rejected
  PING, so the authorized single drawing sequence has not yet begun.
- Second foreground launch passed its PING/STATUS readiness gate and executed
  the one authorized drawing sequence. All 282 arm commands returned DONE:
  one gripper command, four home/first-point/pen-down sequences, 265 line
  segments and four pen-up commands. All eight pauses ran; process exit 0.
  No motion FAULT/REJECTED/UNKNOWN/timeout or automatic retry occurred.
- The agent continuously polled the foreground process and reported milestones
  under the operator's current-test supervision authorization. Periodic existing
  console snapshots kept the chassis enabled_stopped/idle, zero velocity and a
  healthy connection. The console arm client remained offline throughout the
  standalone run; no separate UART or competing arm client was used.
- Asked for operator direction/contact/trajectory observation during the first
  stroke and for physical final drawing/pen-lift confirmation after completion.
  No observation reply has yet been supplied, so this is command-path evidence,
  not verified paper accuracy, contact pressure or physical pen clearance.
- No extra home, jog, gripper release, restart or alarm clear followed the job.
  Restored only the original console arm session after the demo closed cleanly.
  At 14:40:28 +08:00, final sample 317 was valid/fresh (age 0): arm ready/idle,
  motion permitted, YOLO, last_error=none. Chassis remained enabled_stopped,
  zero velocity, idle. Video/backend/ESP32 services were not restarted.
- Final measured joints: [-122.50563,1.96949971,-84.9403992,-97.0290985,
  -32.5056343,90]. Pose in User/Tool 0/0: [-219.907865,-84.7529646,272.6681,
  -44.3547931,-90,44.3547931]. The pose is not a calibrated drawing-error metric.
- A later fresh console sample 343 reported the same joints/pose and no error;
  chassis remained stopped. Final input hash still matches. git diff --check
  passed; no runtime/configuration/data changes or unrelated staging.

## Remaining acceptance and publication

The operator subsequently confirmed that the picture was completely drawn,
while reporting that execution was too slow. This accepts visual completeness,
not quantified accuracy, pen pressure, or separately stated final pen clearance.
No automatic repeat is authorized. Continuous blending, metrology, emergency
stop actuation, link-loss behavior, and coordinated L4 operation were not tested.
The pre-motion handoff rejection is a separate reliability signal; no runtime
repair was made or claimed. Commit only this factual plan and the new log hunk
to the current drawing branch, preserving all unrelated dirty work.
