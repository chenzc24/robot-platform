# PC AprilTag board localization v1

> This page describes the full four-corner PnP diagnostic path. The current
> one-dimensional drawing production path uses the center-delta zero reference
> in `localization-state-machine.md`; it does not depend on camera intrinsics or
> fitted tag-corner orientations.

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
reprojection, finite-value and positive-depth checks and both calibration files
are explicitly marked `production_ready: true`.

The constrained rail localization reads the camera origin back in the board
frame and keeps only the configured translation axis:

```text
rail_position_mm = T_board_from_camera[rail_axis][3]
```

The resulting versioned task context is described in the
[localization state machine](localization-state-machine.md). The relocation
delta needs no camera-to-base or Tool0-to-pen matrix. Do not connect it to
motion until the physical corner convention, camera intrinsics, rail axis,
JSON-origin position, TCP and workspace checks have been validated separately.

## Calibration files

Create ignored local copies:

```powershell
Copy-Item config\apriltag-board.example.json config\apriltag-board.local.json
Copy-Item config\camera-calibration.example.json config\camera-calibration.local.json
```

The tracked examples deliberately have `production_ready: false`. They may be
used for preliminary boxes and a tentative transform, but the result is forced
to `status: precalibration` and `accepted: false`. Measure and replace every
assumed value before changing either flag to `true`.

The camera example is an initial GC4653 pinhole estimate referenced to the
sensor's supplied native 2560 x 1440 mode. It uses the supplied H81-degree and
V51-degree fields of view:

```text
fx = (2560 / 2) / tan(81 degrees / 2) = 1498.687444 px
fy = (1440 / 2) / tan(51 degrees / 2) = 1509.511392 px
cx = 1280 px, cy = 720 px
```

For the current aspect-preserving 1280 x 720 runtime stream, the localizer
scales this to `fx=749.343722`, `fy=754.755696`, `cx=640`, `cy=360`; the runtime
numerics therefore remain identical to the earlier stream-sized estimate.
The independent `3.05 mm / 2.0 um = 1525 px` focal-length estimate is close but
not identical because the published focal length, field of view, pixel pitch
and active image area are rounded specifications. The file uses the effective
horizontal/vertical FOV pair and remains explicitly provisional.

The supplied 5% lens-distortion specification is not an OpenCV Brown distortion
vector: it does not state sign, reference radius, radial model or tangential
terms. The example therefore retains `[0,0,0,0,0]` placeholders and names the
distortion as unknown instead of treating zero as measured. This estimate does not
capture the real lens, focus, assembly tolerance, ISP crop or distortion and
must not be treated as metric camera calibration.

Camera calibration records the intrinsic matrix and distortion coefficients at
its calibration image size. Runtime frames with the same aspect ratio may be
scaled; a different aspect ratio is rejected instead of silently stretching
the intrinsics.

The board file stores every tag's four physical corner coordinates in
millimetres in the `drawing_board` frame. Corner order is the decoded marker's
canonical top-left, top-right, bottom-right and bottom-left order—not whichever
corner happens to appear at the top-left of a tilted image. The default example
uses four 40 mm tags with the same printed orientation at the corners of a
300 x 200 mm outer rectangle. These dimensions are unmeasured placeholders, not
a print specification. Version 1 requires all stored tag corners to be coplanar.
The same layout schema may instead contain eight or more unique tags distributed
along a longer rail. They share one board frame and need not all be visible in
the same image; overlapping adjacent tag groups are preferred.

For the eight-tag rail layout, the observation-only
[board calibration tool](apriltag-board-calibration.md) can hold four measured
outer anchors fixed and infer the four middle tags from multiple stopped,
overlapping views. It outputs a separate review-required board and residual
report; it does not change runtime configuration or replace camera calibration.

## Console configuration

Use schema version 5 in ignored `config/console.local.json`, copy the `vision`
section from `config/console.example.json`, then set `enabled` to `true` after
copying the local files. Schema 3 and 4 files remain loadable but cannot enable
the new localization lock. Unready defaults produce only `precalibration`
output; measured files may be marked ready later. Important tunables are:

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
the board-origin translation in camera coordinates. It appends `UNVERIFIED
DEFAULTS` whenever either readiness flag is false. The full matrices are in
the state API and structured JSON-lines log at `logs/vision/apriltag.log`.
Status changes are logged immediately and solved poses are rate-limited to one
record every two seconds.

The overlay and WebRTC player consume the same underlying RTSP source through
separate receive paths. Their frames are not timestamp-synchronized in v1, so a
moving camera can show a small box/video offset. Board localization must be
frozen only after the chassis is stopped and several stable observations have
been checked. The state machine now performs that stopped/settled/stable-window
lock, but exact frame correlation remains follow-up work.

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
