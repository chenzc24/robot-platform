# Run AprilTag live UI observation and monitor logs

- Status: completed
- Responsible: agent execution with user observing the physical camera scene
- Highest validation level: L2

## Objective

Enable the observation-only AprilTag worker in the existing local console
configuration, restore or reuse the owned MaixCam video source and PC relay,
open the localhost UI, verify live video/overlay/status without device-control
connections, and monitor the relevant structured logs while the user presents
tags to the camera.

## Initial state of the workspace

```text
## target/apriltag-pc-calibration-v1...origin/target/apriltag-pc-calibration-v1
 M .vscode/settings.json
 M app/demo.py
 M plan/log.md
?? plan/2026-09-03-arm-xyz-singularity-diagnosis/
?? plan/2026-09-03-arm-yz-drawing-review/
?? plan/2026-09-03-video-stream-diagnosis/
```

These paths predate this L2 goal and remain protected. The working branch and
PR already contain the AprilTag v1 and safe GC4653 precalibration commits.

## Modifiable files

- ignored `config/console.local.json`, limited to `vision.enabled`
- owned local process state and ignored logs under `logs/`
- this plan and a new appended `plan/log.md` section
- AprilTag PC runtime/tests/docs only if live evidence exposes a bounded defect;
  update this plan before any such source edit

## Read-only files and directories

- `.vscode/settings.json`, `app/demo.py`, prior diagnostic plans/log hunk
- existing endpoint, credential, motion, chassis and arm fields in local config
- `ESP32/`, `Camera/`, `Robot Arm_Claws/`, `tmp/`
- device source files, firmware, boot settings, TCP232 and robot-arm projects
- all chassis and robot-arm command/control routes

## Shared dependencies

- MaixCam GC4653 source service at the documented `/live` RTSP endpoint.
- Owned local FFmpeg/MediaMTX relay and loopback RTSP/WebRTC endpoints.
- Ignored GC4653/default-board inputs remain `production_ready: false`, so live
  results must stay `precalibration` and `accepted=false`.
- Console and vision logs: `logs/console/web-events.log`,
  `logs/vision/apriltag.log`, and owned relay logs.
- Computer-use skill is used only to inspect the browser window after the
  services are started through repository-owned commands.

## Risk and safety gate

- Risk: L2 camera/network/process ownership. The action may open an additional
  RTSP receiver but has no motor, arm, gripper, UART, CAN or command-session path.
- Hardware: powered MaixCam camera only; verify reachability and current process
  ownership before starting anything.
- User operations: user requested UI camera takeover and will present tags.
- Backup and recovery: no device file writes. Stop only PID/state files proven
  to belong to this repository's video relay/console; existing source start
  script is idempotent for its owned PID. Physical MaixCam restart is not planned.
- Motion gate: not applicable. Do not click chassis/arm connect or motion UI.

## Expected work

1. Inspect local ports/PIDs/logs and MaixCam video status without motion.
2. Enable only local AprilTag vision, then start/reuse the owned source, relay
   and localhost console in that order.
3. Inspect the browser live viewport and `/api/state`; confirm the vision worker
   reports frames or a specific fault and that unready data is never accepted.
4. Keep a bounded live tail on AprilTag, console and relay logs while the user
   tests tag visibility; report meaningful changes without flooding.
5. Record exact L2 evidence, process state and any residual issue.

## Validation

- local PID/port ownership and MediaMTX path readiness
- bounded RTSP receive probe without motion
- `GET /api/state` vision status, counts, confidence and readiness flags
- browser screenshot/state inspection without device-control actions
- bounded structured-log observation
- `git diff --check` and `git status --short --branch`

## Actual results

- Initial inspection found no listener on ports 8080, 8555 or 8889, a stopped
  local relay, and a stale MaixCam video PID. The test enabled only the ignored
  local `vision.enabled` field, then started the owned MaixCam source, local
  relay and web console. No device-control connection was opened.
- The bounded RTSP probe received 108 1280 x 720 frames in 6.015 seconds at
  20.007 fps; first-frame time was 2.109 seconds.
- Browser inspection confirmed live video, ID-labelled yellow tag outlines,
  confidence/RMSE output and the `UNVERIFIED DEFAULTS` warning. A stationary
  board showed the overlays aligned after the 90-degree display transform.
  During board motion the 5 fps inference overlay visibly lagged the independent
  20 fps WebRTC view; this was temporal mismatch, not a rotation mapping defect.
- The run produced 270 localization records, 245 with tags and all IDs 0-3.
  The 44 single-tag records had quality scores 0.563-0.858 and reprojection
  RMSE 0.022-1.196 px. There were 201 multi-tag records and the lowest tagged
  quality sample was 0.510. No `vision_failed` event occurred.
- Multi-tag poses were usually rejected for excessive reprojection error or
  invalid pose geometry because the physical ID placement does not match the
  placeholder 300 x 200 mm board model. No result was accepted because both
  calibration inputs remain deliberately unverified.
- Live API samples showed roughly 56-189 ms processing time. The configured
  `detection_fps` is explicitly 5.0 while video is 20 fps, explaining much of
  the perceived low update rate. One clear `no_tags` sample still reported 114
  rejected candidates, so intermittent decoding requires instrumentation and
  detector review rather than lowering the confidence threshold blindly.
- At the user's stop request, the monitor, console PID 40060, FFmpeg PID 41064,
  MediaMTX PID 46700 and MaixCam RTSP PID 939 were stopped. Ports 8080, 8555 and
  8889 were closed. The forced local process stop did not append a
  `vision_stopped` event; the preceding run contains no failure event.
- L2 completed without chassis/arm connection, command, deployment or motion.
  No runtime source file was changed during this live goal.

## Outstanding matters

- Measure the physical corners/ID layout and run a real GC4653 intrinsic and
  distortion calibration before using any transform.
- In a separate bounded performance goal, log per-frame processing time, tag
  edge size, candidate counts and frame timestamps; benchmark higher inference
  rates and consider a same-frame annotated stream or timestamp-aware overlay.
- Add a graceful console shutdown path if a guaranteed `vision_stopped` record
  is required.

## Experience signal (for manual review)

- Candidate signal only: an independent low-rate inference stream over a
  higher-rate display stream can look like incorrect geometry during motion.
  Static-frame inspection distinguished it here; do not create a lesson from a
  single run.

## Intent to submit

```text
docs(vision): record AprilTag live UI L2
```
