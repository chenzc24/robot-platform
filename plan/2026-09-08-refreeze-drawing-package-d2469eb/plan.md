# Refreeze the current drawing deployment package

- Status: complete
- Responsible: joint
- Highest validation level: L1

## Objective

Freeze clean `main` commit `d2469eb` into a new hash-verifiable drawing
deployment bundle. Preserve the unchanged ESP32, MaixCam and robot-arm payloads,
include the current 700 x 200 mm PC drawing template, and add a default-deny
Baseline control template whose initial JSON-axis offset remains a PC-side
field measurement.

## Initial audit

- `main` is clean and synchronized with `origin/main` at `d2469eb`.
- The existing `drawing-97253c9` bundle is intact, but its PC drawing template
  is 150 x 150 mm and its source commit predates bounded 300 mm relocation hops.
- Device-side source has not changed between `97253c9` and `d2469eb`.
- No drawing or drawing-control local configuration currently exists. Existing
  local device configuration, credentials and AprilTag files remain untouched.

## Editable scope

- new ignored outputs `build/drawing-d2469eb/`, `.zip`, and `.zip.sha256`
- `docs/deployment/2026-09-08-current-drawing-package.md`
- `docs/deployment/2026-09-08-current-drawing-package.json`
- `docs/deployment/README.md`
- this plan and append-only `plan/log.md`

## Read-only scope and dependencies

- all product source and tracked configuration templates under `protocol/`,
  `src/`, `tools/`, `app/`, and `config/`
- all older build outputs and device backups
- all local configuration and secrets
- every physical device and protected raw-resource archive

## Validation

- compare every packaged runtime/template byte with its declared source or
  generated expectation
- build the DobotStudio project twice and compare all four files
- parse all JSON, compile applicable Python, check shell syntax
- run applicable device/protocol/robot-arm and drawing tests
- verify directory/ZIP equality and final SHA-256
- secret/staged-scope review, `git diff --check`, and final branch sync

## Safety

L1 only. No discovery, connection, upload, controller import, reset, service
action, configuration write or motion. `initial_json_axis_offset_mm=0` in the
Baseline template is an inactive placeholder, not a measured site value.

## Commit intent

Commit and push the refreshed package metadata directly to the sole `main`.

## Actual results

- Generated ignored `build/drawing-d2469eb/` with 42 manifest payloads and 44
  total files including `DEPLOY.md` and `manifest.json`. Generated the matching
  ZIP and SHA-256 sidecar.
- The three device payloads are 14 ESP32 files, 15 MaixCam arm/video files and
  a four-file freshly generated DobotStudio project. Device payload bytes are
  unchanged from the preceding freeze and match current source/generated output.
- The PC drawing template is 700 x 200 mm. Added
  `drawing-control.baseline.example.json` with `selected_mode=baseline`,
  `production_ready=false`, a 300 mm per-hop limit and inactive
  `initial_json_axis_offset_mm=0`. It contains no site measurement.
- All 42 payload hashes match the manifest. Thirty packaged Python files compile,
  four shell files pass syntax checks, all JSON parses, 37 copied files match
  their current source bytes, and a second arm build matches all four outputs.
- All 386 repository tests passed. All 44 ZIP entries match the directory bytes.
  Final ZIP SHA-256:
  `6cdd35e7c3b6f10661ac29f353408b4190857db7e5dbedaf22d9f5e249dd1e66`.
- The packaged 700 x 200 drawing and Baseline control templates passed the
  unified runner dry-run on the 439-stroke / 3,903-point real sample. It selected
  Baseline, required no AprilTag lock and stopped at the expected first window
  checkpoint without opening a device connection.
- No hardware discovery, connection, upload, controller import, reset, service
  action, local configuration change or motion occurred.
