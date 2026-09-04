# PC AprilTag board localization v1

## Boundary and result

This first version is observation-only. The computer reads the existing local
RTSP route in parallel with the browser's WebRTC preview, detects AprilTag
36h11 markers, estimates the drawing-board pose and publishes the latest result
to the localhost console. It contains no chassis or robot-arm command call.

The central output is:

```text
p_camera = T_camera_from_board * p_board
p_board  = T_board_from_camera * p_camera
```

Both 4 x 4 matrices, the board-origin translation in camera millimetres,
rotation vector, reprojection RMSE, used tag IDs and a `0..1` confidence value
are available in `GET /api/state` under `vision`. The confidence is a quality
score, not a calibrated probability. `pose_solved` means a mathematical pose
was found; `accepted` additionally means it passed the configured confidence,
reprojection, finite-value and positive-depth checks.

This output is not yet the arm-base transform. After the fixed camera-to-base
extrinsic is measured, compose it as:

```text
T_base_from_board = T_base_from_camera * T_camera_from_board
```

Do not connect either matrix to motion until the physical corner convention,
camera intrinsics, camera-to-base extrinsic, TCP and workspace checks have been
validated separately.

## Calibration files

Create ignored local copies:

```powershell
Copy-Item config\apriltag-board.example.json config\apriltag-board.local.json
Copy-Item config\camera-calibration.example.json config\camera-calibration.local.json
```

The tracked examples deliberately have `production_ready: false`; the camera
example also has unusable zero focal lengths. Measure and replace every value
before changing this flag to `true`.

Camera calibration records the intrinsic matrix and distortion coefficients at
its calibration image size. Runtime frames with the same aspect ratio may be
scaled; a different aspect ratio is rejected instead of silently stretching
the intrinsics.

The board file stores every tag's four physical corner coordinates in
millimetres in the `drawing_board` frame. Corner order is the decoded marker's
canonical top-left, top-right, bottom-right and bottom-left order—not whichever
corner happens to appear at the top-left of a tilted image. The example assumes
four tags with the same printed orientation; it is only a layout illustration.
Version 1 requires all stored tag corners to be coplanar.

## Console configuration

Use schema version 4 in ignored `config/console.local.json`, copy the `vision`
section from `config/console.example.json`, then set `enabled` to `true` after
both local calibration files are ready. Important tunables are:

- `detection_fps`: PC inference rate; it does not change the WebRTC frame rate.
- `min_tag_edge_px`: projected-size quality reference for oblique or distant tags.
- `max_reprojection_error_px`: geometric rejection threshold.
- `min_confidence`: adjustable acceptance threshold; there is no fixed minimum
  visible-tag count. One good known tag can solve a pose, while multiple spread
  tags normally improve coverage and robustness.
- `stale_after_ms`: removes acceptance from an old result while retaining it for
  diagnosis.

The score combines minimum projected tag edge, distance from the image border,
spatial coverage, visible known-tag count and reprojection error. OpenCV's
detector does not expose AprilTag `decision_margin` or decoded Hamming distance,
so those are not falsely presented as available measurements in this version.
Thresholds must be tuned from images captured at the real distance, tilt,
lighting, focus and motion blur.

## UI and logs

The console draws each latest detection on its transparent video layer:

- green: known tag in an accepted pose;
- amber: known tag but the latest pose is not accepted;
- grey: detected ID absent from the board layout.

The top-left badge displays status, confidence, reprojection RMSE, used IDs and
the board-origin translation in camera coordinates. The full matrices are in
the state API and structured JSON-lines log at `logs/vision/apriltag.log`.
Status changes are logged immediately and solved poses are rate-limited to one
record every two seconds.

The overlay and WebRTC player consume the same underlying RTSP source through
separate receive paths. Their frames are not timestamp-synchronized in v1, so a
moving camera can show a small box/video offset. Board localization must be
frozen only after the chassis is stopped and several stable observations have
been checked. Exact frame correlation is follow-up work.

## Standalone app

The reusable implementation is under `src/console/vision/`; the convenient app
entry is:

```powershell
.\.venv\Scripts\python.exe app\apriltag_calibration.py `
  --source rtsp://127.0.0.1:8555/maixcam `
  --board config\apriltag-board.local.json `
  --camera config\camera-calibration.local.json `
  --result-json logs\vision\latest-pose.json
```

It prints complete JSON results and writes a rate-limited structured log. An
image path may be supplied instead of RTSP for offline checks. The command is
observation-only and does not open a robot-arm or chassis session.
