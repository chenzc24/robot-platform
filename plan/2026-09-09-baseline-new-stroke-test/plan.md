# Import and run the new baseline stroke test

- Status: blocked (new controller project is built, but the LAN2 deployment target is unreachable)
- Responsible: joint
- Highest validation level: L3

## Objective

Import the user-provided `strokes_testnew.json` as a version-controlled drawing
test, validate its JSON and physical-canvas compatibility, then perform one
attended Baseline run only if its dry run and runtime safety gates pass.

## Initial audit and scope

- `main` is synchronized with `origin/main`; `.vscode/settings.json` is an
  unrelated user-owned local change and remains read-only.
- The imported source is
  `C:\Users\90590\xwechat_files\wxid_2a0c1fzfb4n122_d17b\msg\file\2026-09\strokes_testnew.json`.
- The source currently has invalid JSON syntax and declares a 210 x 210 mm
  canvas. The user explicitly authorized non-uniform physical mapping of this
  test to the configured 700 x 200 mm canvas; this is recorded in the imported
  test metadata rather than silently applied by the runner.

## Editable scope

- `dataset/strokes_testnew.json`, preserving the supplied normalized stroke
  geometry, making only required JSON-syntax repairs, and updating its physical
  target metadata to the explicitly authorized 700 x 200 mm mapping
- ignored `config/drawing.local.json` and `config/drawing-control.local.json`,
  limited to temporarily opening their production-ready gates for this
  user-authorized attended test and restoring them after the run
- `build/drawing-34488b57/robot-arm/DobotStudio/`, a new generated controller
  project only; it must retain a separate project identity and never overwrite
  `build/drawing-d2469eb/robot-arm/DobotStudio/`
- this plan and its factual results
- `plan/log.md` only after validation, if no concurrent plan owns it

## Read-only scope and dependencies

- all runtime/device source, protocol, local drawing/control/console
  configuration, MaixCam release, ESP32 release, the existing controller
  project and raw resources
- the user-provided source attachment after import

The test depends on the existing Baseline runner and its selected local device
configuration. A 210 x 210 mm job cannot silently execute against a 700 x 200
mm physical canvas because that would be non-uniform scaling.

## Safety and validation

- L0: parse the imported JSON, inspect geometry and run the guarded dry run
- L2: query runtime health only if required by the runner
- L2: send one `arm.stroke_begin` capability probe without `stroke_execute`;
  it can stage controller data but cannot command a robot move
- L2: back up/export the current LAN2 controller project, import and start the
  separately named generated project, then require fresh PING, STATUS and a
  no-execute staged-stroke terminal response before any drawing run
- L3: the user has confirmed an on-site operator, emergency stop, clear area,
  restrained/clear chassis, confirmed arm pose and the expected Baseline
  drawing action. Before any motion, re-check the runner's explicit safety
  admission, exact job hash, fresh log and device readiness.
- No motion will be sent if JSON, physical dimensions, runtime handshake or
  an explicit runner gate fails. No automatic retry follows an unknown outcome.

## Completion boundary

Record the imported-file hash, syntax corrections, dry-run result, any real
device result and residual risks. Commit only declared files after reviewing
the complete diff and leave the user-owned VS Code change untouched.

## Actual results

- Imported `dataset/strokes_testnew.json` from the supplied attachment. The
  source had missing coordinate commas and one trailing comma; the imported
  asset repairs syntax only, retains all 8 supplied strokes / 16 points, and
  records the user's explicit non-uniform 700 x 200 mm physical mapping.
- The asset is valid JSON, has SHA-256
  `4e58c243d0b45c2284d7974aa0446abc375bc87262a99f68d11eea123addc755`, and
  the guarded dry run completed without a device connection. Its job hash is
  `34488b57de137444874e37c08225ffb28e1d9e0707432cb3992440553b42d3c6`.
- Read-only checks found ESP32 online and the arm gateway/controller PING and
  status initially `DONE`, with controller `service_state=ready`,
  `motion_enabled=1` and valid feedback.
- Before opening any production gate, the runner's required non-motion
  staged-stroke capability probe (`arm.stroke_begin`, without execute) did
  not receive a terminal result and was classified as `outcome_unknown`.
  A subsequent read-only arm status query ended `FAULT/response_timeout`.
  No retry, production-gate modification, `stroke_execute`, robot arm motion,
  chassis command or controller deployment occurred.

## Blocker and recovery

The active controller is not proven compatible with the staged-stroke RPA2
protocol that the active PC and MaixCam releases require. Treat the staged
state as unknown, restore or deploy the compatible controller project through
its separate LAN2 maintenance procedure, then confirm fresh PING/STATUS and a
non-motion capability response before asking for a new attended Baseline run.

## Controller deployment amendment

The user explicitly authorized generation and LAN2 deployment of a new
controller project. It will be built from the current reviewed staged-stroke
source, as a separate DobotStudio project, with `YOLO_MODE=True` and
`MOTION_ENABLED=True` to retain the active engineering-control acceptance
policy. This changes no joint/pose limits, taught points, tool/user frames,
Home pose or PC drawing mapping. A recoverable export of the current controller
project is required before its replacement service is started.

## Controller-project build result

- Generated the new isolated DobotStudio project at
  `build/drawing-34488b57/robot-arm/DobotStudio/`. Its generated `main.py`
  contains `STROKE_BEGIN`, `STROKE_APPEND` and `STROKE_EXECUTE`; its explicitly
  reviewed `var.py` sets `YOLO_MODE=True` and `MOTION_ENABLED=True` for this
  attended test. Python syntax compilation passed.
- The legacy build directory remains unchanged. Before a controller write, the
  PC's LAN2 interface was verified as `192.168.200.10/24`; the configured arm
  target `192.168.200.1` did not answer one ICMP probe, and no DobotStudio
  application window was available for export/import. No controller connection,
  project export, import, start, device write or physical motion occurred.
- Reconnect the LAN2 cable/target and open DobotStudio. Then export the active
  controller project, import this new separate project and start it before the
  non-motion PING/STATUS/staging handshake.
