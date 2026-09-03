# Align arm query timing and launch the attended web console

- Status: implementation and L2 complete; operator acceptance in progress
- Branch: `target/arm-timeouts-manual-ui`; baseline `c6a2a6d`
- Risk/validation: L1 and live L2; the operator performs any later L3 motion
- Initial audit: only user-owned `.vscode/settings.json` is dirty; preserve it

## Scope

Editable: `src/console/maixcam_arm_client.py`,
`src/console/web_console/runtime.py`, `tools/robot_cli.py`, matching console/dev
tests, `config/console.example.json`, console/arm deployment documentation,
this plan and `plan/log.md`, ignored local config/launch helpers/logs.
The configured MediaMTX 1.20.0 and FFmpeg 9.0.1 binaries are missing; restore
those exact releases to ignored `.tools/` from their publisher release pages,
verify publisher checksums, and retain download evidence locally.
Inspect but do not modify: device runtime sources/files, firmware, CAN and
TCP232 parameters, credentials, protocol framing, taught points, user settings.

The operator requests longer timeouts and running MaixCam, ESP32, arm and PC
services with the full approved manual UI. Existing limits remain 600 mm/s,
800 mrad/s, arm YOLO with 1..100% speed/acceleration. Do not set initial speed
sliders to maximum or send Enable/motion/gripper commands on the operator's
behalf. Device services are already deployed; no redeployment is planned.

## Implementation

1. Set shared arm PING/STATUS TTL to 5000 ms. Align the socket response budget
   with each request TTL plus a transport margin, without automatic retries;
   keep connection establishment timeout separate. Existing 60 s motion TTL
   remains unchanged. Wire schemas, device limits and ESP32 health stop do not
   change; gateway/controller already honor the request TTL.
2. Separate PC chassis-health and arm-status workers. Slow arm reads must not
   delay the 500 ms chassis health cycle. Keep one arm request in flight and
   skip background polls while the arm route is occupied by an operator call.
3. Validate regression tests for deadlines, no retries, and blocked-arm health
   independence. Check the current UI configuration exposes approved ranges.
4. Verify existing device services via non-motion queries. Start the local
   MediaMTX relay and web service using the preserved credential only in the
   child environment; never print it or put it in launch arguments.
5. Connect both UI sessions through the existing HTTP API, retain chassis
   disabled, verify repeated measured feedback and healthy chassis polling,
   and open the browser for the operator. No agent-generated movement.

## Validation and records

Run focused tests followed by console/dev suites, syntax and diff checks,
live CLI PING/STATUS, direct/relay video checks, and browser/API inspection.
Record actual service state, faults, and pending L3/UI manual acceptance.
Review the complete diff, stage only declared files, commit/push this branch;
do not merge `main` or stage local secrets/generated output/user settings.

## Live recovery adjustment

During relay startup the existing video process exited. Its log records
`exit app by KEY_OK` followed by `rtsp_stopped`; the source port no longer
provides frames. Resume only the identified video service with its existing
start script (no device source/config write). Temporarily disconnect the PC
arm session during MaixPy's transient default-UART initialization, then restore
it; do not restart the gateway, controller, or ESP32. Preserve stop/start logs.

## Actual results

- Changed only the shared PC arm client and web health scheduling, with six
  new regression tests. No device runtime source, protocol schema, motion
  limit, controller setting, or credential file was modified.
- L1: 37 runnable console tests and 25 dev tests passed. Full console discovery
  additionally hit two import errors in the legacy Qt modules because this
  environment lacks PySide6; those modules were not validated. The web backend
  does not require PySide6. Focused deadline and worker tests passed.
- Final rerun: all 62 runnable tests passed again; the four affected Python
  files passed compilation and `git diff --check` passed. Reviewed source,
  test and documentation diffs contain no credentials or generated artifacts.
- Default CLI `arm check --json` now returns READY, PONG and measured STATE
  without a TTL override. ESP32 read-only probe returned v3 ready/disabled.
- The web backend was launched with the preserved credential in its child
  environment only, then both device sessions connected. No Enable, nonzero
  velocity, arm motion or gripper command was sent by the agent. Browser blur
  can send the existing chassis STOP action.
- Repeated web status reads showed chassis online/authenticated and independent
  health updates (61 ms in one sample), arm ready/YOLO with valid measurements
  and increasing sample IDs (5 through 165 observed). Do not interpret this
  as a guaranteed polling frequency or verified terminal motion position.
- Restored only the existing video service after its KEY_OK exit: video PID
  1662; gateway PID 1415 and ESP32/controller services were not restarted.
  Local relay started with MediaMTX PID 15684 and FFmpeg PID 6400. These IDs are
  observations, not stable service identifiers or unconditional kill targets.
- Local RTSP decode: 41 frames, 1280 x 720 H.264, 19.99 media fps over a 4.016 s
  probe (first frame at 3.532 s). Browser inspection confirmed the embedded
  WebRTC picture after page reload. The agent initially clicked the rotation
  button while looking for reload; no motion control was clicked. The operator
  continued using the page, so do not overwrite their current view or inputs.
- The operator used the live UI while validation continued. Its journal shows
  joint jog, absolute joint, chassis velocity and gripper commands with DONE.
  These are protocol observations, not an agent-run L3 acceptance or proof of
  physical execution. A subsequent status contained `last_error=invalid_gripper`
  while the fault list was empty: gripper behavior/error surfacing remains an
  explicit unresolved item and must not be reported as accepted.
- The web UI remains running at `http://127.0.0.1:8080/`, with approved chassis
  limits 600 mm/s and 800 mrad/s and arm YOLO controls available. Chassis was
  disabled in the latest non-motion status sample; the operator controls Enable.
- Runtime evidence stays ignored under `logs/console/`, `logs/arm-l2/`,
  `.device-cache/` and `tmp/`. User `.vscode/settings.json` remains untouched.

## Restored media dependencies

Publisher releases: [MediaMTX v1.20.0](https://github.com/bluenviron/mediamtx/releases/tag/v1.20.0)
and [FFmpeg 9.0.1 Windows build](https://github.com/GyanD/codexffmpeg/releases/tag/9.0.1).
Downloaded archives matched the GitHub release asset SHA256 before extraction:

- MediaMTX: `7364e7672e6b4420e986ec4b56e2cc32ec7b4085f69b56ec224d596d0fa8b19f`
- FFmpeg: `fec81ae03971d9dd4be3ebe02e263bd2ec1d789483f931bdba5f5715e65da2e9`

Both extracted executables reported the expected versions. A redundant FFmpeg
download was interrupted after extraction; its remaining archive is incomplete
and is not a verified reusable package. Running binaries come from the earlier
verified extraction. All artifacts remain in ignored `.tools/`.

## Handoff

Review/syntax/diff validation and scoped commit/push close this bounded goal.
Keep device and PC services running. Do not merge main. Physical motion,
gripper acceptance, full L3/L4, cold boot and the legacy Qt suite remain outside
the completed validation. The gripper error/lifecycle discrepancy requires a
separate bounded investigation, not a live controller edit during manual use.
