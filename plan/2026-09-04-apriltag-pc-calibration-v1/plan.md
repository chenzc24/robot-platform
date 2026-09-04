# PC AprilTag board localization v1

- Status: completed
- Responsible: agent implementation, user supplies measured calibration data
- Highest validation level: L1

## Objective

Add a computer-side AprilTag 36h11 observation pipeline that reads the existing
RTSP stream, detects known board tags, estimates the board-to-camera transform,
publishes an explicit quality score and pose acceptance state, logs useful
localization evidence, and draws the latest tag observations over the existing
web-console video. This first version is observation-only and must not issue any
chassis or robot-arm command.

## Initial state of the workspace

`git status --short --branch` at goal entry:

```text
## main...origin/main
 M .vscode/settings.json
 M app/demo.py
 M plan/log.md
?? plan/2026-09-03-arm-xyz-singularity-diagnosis/
?? plan/2026-09-03-arm-yz-drawing-review/
?? plan/2026-09-03-video-stream-diagnosis/
```

The settings and drawing-speed edits are user work. The pre-existing log hunk
and three diagnostic directories are earlier work. They do not overlap the new
vision module, configuration template, web overlay, or tests. Preserve them and
stage only this goal's files and eventual appended log hunk.

## Modifiable files

- `app/apriltag_calibration.py`
- `src/console/vision/`
- `src/console/runtime_config.py`
- `src/console/web_console/`
- `config/console.example.json`
- `config/apriltag-board.example.json`
- `config/camera-calibration.example.json`
- `.gitignore`
- `requirements-dev.txt`
- directly related tests under `tests/console/` and `tests/app/`
- `docs/console/control-console-ui.md`, `docs/maixcam/video.md`, `app/README.md`
- this goal plan and a new appended section in `plan/log.md`

## Read-only files and directories

- `.vscode/settings.json`, `app/demo.py`, and all pre-existing uncommitted work
- `ESP32/`, `Camera/`, `Robot Arm_Claws/`, and `tmp/`
- device filesystems and all deployed processes
- chassis, robot-arm, MaixCam gateway, and MaixCam video-service source
- shared motion protocols and safety limits

## Shared dependencies

- The architecture in `docs/overall-plan.md`: PC owns vision inference;
  MaixCam remains the video producer and arm gateway.
- Existing local RTSP input and independent MediaMTX WebRTC preview.
- OpenCV AprilTag 36h11 detection and calibrated PnP conventions.
- User-provided camera intrinsics/distortion and measured tag-corner coordinates
  in the board frame. Example values are not production calibration.
- Browser preview is clockwise 90 degrees by default and letterboxed; overlay
  coordinates must follow the displayed frame geometry.

## Risk and safety gate

- Risk: PC-only vision code and UI/configuration changes. A bad calibration can
  produce a numerically valid but physically wrong transform, so the result is
  labeled observation-only and separated into `pose_solved` and `accepted`.
- Hardware: none required for L1. No network connection or video-process start
  is needed for deterministic tests.
- User operations: install the pinned PC dependency, measure the board layout,
  and supply camera calibration before live pose output can be trusted.
- Backup and recovery: Git rollback of scoped PC files; no device state changes.
- Motion gate: not applicable. The implementation has no motion-call path.

## Expected work

1. Define strict, secret-free camera and board calibration JSON models.
2. Implement AprilTag detection, known-corner aggregation, planar pose solving,
   reprojection metrics, quality scoring, and JSON-safe transform output.
3. Add an RTSP worker and standalone app entry with rate-limited structured logs.
4. Publish vision state through the console and draw frame-aware overlays plus
   concise pose/quality status in the existing video panel.
5. Add offline synthetic/unit/browser checks and update operating documentation.

## Validation

- `git diff --check`
- `git status --short --branch`
- Python syntax/import checks for changed modules
- focused unit tests using generated AprilTag images and synthetic camera/board
  correspondences; no camera or device connection
- web console tests for sanitized vision state and overlay assets
- existing console and app suites, plus JavaScript syntax/tests

L1 covers deterministic detection, transform conventions, scoring, config
fallback, serialization and UI rendering. Live oblique-angle detection, camera
metrology, RTSP/WebRTC frame latency and physical board accuracy remain future
L2 evidence and must not be reported as passed here.

## Actual results

- Added strict production-ready camera/board JSON loaders, AprilTag 36h11
  detection, single/multi-tag planar IPPE pose solving, inverse transforms,
  per-tag reprojection diagnostics and a configurable five-part quality score.
- Added an observation-only RTSP worker, structured/rate-limited JSONL logs and
  `app/apriltag_calibration.py` for image or RTSP JSON output. OpenCV 4.14.0.94
  and NumPy 2.5.2 were installed into the ignored project virtual environment.
- Added web state publication, stale-result handling, tag canvas overlay,
  letterbox/90-degree display mapping and concise confidence/pose UI status.
- L1 passed with one unified system-Python run: 308 Python tests across app,
  console, dev, ESP32, MaixCam, protocol and robot-arm suites. The project
  virtual environment separately passed all seven new AprilTag tests and the
  CLI help/import check. Fourteen JavaScript tests and `node --check` passed.
  `git diff --check` passed apart from informational Windows LF/CRLF notices.
- Synthetic checks covered generated-tag decoding, strongly oblique four-tag
  pose recovery, a one-tag accepted solution, transform inversion, strict
  calibration templates, schema-3 compatibility, state staleness and overlay
  letterboxing. No network, RTSP source, device session or motion was used.

## Outstanding matters

- User must provide measured intrinsics/distortion and tag-corner coordinates.
- Camera-to-arm-base extrinsic calibration and motion integration are out of
  scope for this observation-only version.
- Live RTSP/WebRTC overlay alignment, actual tilt/lighting detection limits,
  metric accuracy and confidence-threshold tuning remain L2/metrology work.

## Experience signal (for manual review)


## Intent to submit

```text
feat(vision): add PC AprilTag board localization
```
