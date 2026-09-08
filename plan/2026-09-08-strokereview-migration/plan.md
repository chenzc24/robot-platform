# StrokeReview migration

- Status: in-progress
- Owner: Codex, isolated worktree
- Highest validation: L1; medium software integration risk, no hardware

## Objective
Import the supplied image-to-line-art review workflow as a self-contained computer-side application, retaining image processing, review and normalized stroke export. Provide a repository entry point and document the downstream coordinate contract. The obsolete drawing demo is outside scope per user instruction.

## Workspace audit
Source checkout E:/Device Network is on target/localization-lock-state-machine at 0eec878. All 17 tracked dirty paths and five untracked entries reported on entry belong to another worker, confirmed by user; do not edit, stage or copy them. They include root docs/config/log, app/demo.py and localization code/tests. New worktree E:/Device Network-strokereview, branch target/strokereview-migration, starts clean from committed HEAD 0eec878. Concurrent changes must be reconciled in review, never overwritten.

## Editable scope
- apps/strokereview/**: imported source, local exclusions, migration corrections and source provenance.
- stroke-review.cmd: repository launcher.
- docs/console/strokereview.md and README.md: discoverability and integration contract.
- plan/2026-09-08-strokereview-migration/** and plan/log.md in this worktree only.

## Read-only scope and dependencies
- Original ZIP E:/Downloads/StrokeReview-source-20260904-103816.zip.
- All other existing repository paths, original checkout and other worktrees.
- ESP32/, Camera/, Robot Arm_Claws/ are protected archives.
- Existing device protocol, console, chassis/arm clients and localization are unchanged. This module produces files/HTTP responses and owns no device connections; therefore protocol/, src/esp32/, src/maixcam/, src/console/ and their vectors need no modification.
- Upstream frontend/backend locks, stroke schema, canvas transform and optional model manifests are shared application dependencies.

## Work and safety
1. Inspect and import source with traversal checks, excluding weight binaries, generated files and secrets.
2. Preserve standalone workflow and add root launch/documentation. Check coordinate/export contract without obsolete demo coupling.
3. Run backend tests, frontend tests/build and local API/image smoke checks. Review tracked files for secrets and artifacts.
4. Record actual results, commit only declared files, push branch, open review PR if available and check remote synchronization.

No hardware connections, deployment, motion or cloud paid calls. L2-L4 not required for this source migration; end-to-end coordinated robot execution remains unvalidated. Device responsibility boundaries do not change. Runtime credentials and weights remain local/ignored; original ZIP stays untouched. Recovery is Git revert of this isolated change.

## Validation commitments
- Source manifest/provenance and exclusion review.
- Backend pytest; frontend tests and production build; model-service unit tests if dependencies feasible.
- API processing and export on synthetic input, including non-square canvas contract.
- git diff --check, full diff review and git status --short --branch.

## Actual results
- Imported 95-entry upstream source package with original archive SHA256 and upstream manifest preserved; all original manifest entries verified against the untouched ZIP. Four weight files verified against model manifest and kept locally/ignored; generated Vite outputs excluded.
- Added root launcher and coordinate/usage documentation; retained all algorithm modules, frontend editing/export, model service and packaging source. No obsolete demo or device code changes.
- Found and corrected fixed-port frontend proxy: STROKE_REVIEW_API_URL follows BackendPort. Frozen installation uses uv --locked and npm ci.
- Backend: 48 tests passed (Python 3.13.1); frontend: 33 tests passed, TypeScript/Vite production build passed. The first proxy patch exposed missing Node types during build; replaced direct process access with Vite loadEnv and build passed.
- Model interface tests: 7 passed in the backend Python 3.13 environment, exercising lazy registry/HTTP behavior only. Desktop launcher unit tests: 5 passed. No full Python 3.12 torch/controlnet runtime installation or inference performed.
- L1 loopback smoke: root launcher started backend 18100 and frontend 15273; actual frontend proxy health/schema calls succeeded; synthetic 320x160 PNG processed by classic algorithm via HTTP client and exported two strokes on 200x100 mm canvas. Orders, finite points and normalized bounds verified. Local smoke outputs are ignored.
- Dependencies emit Starlette/httpx and NumPy deprecation warnings; tests pass. Cloud calls, model inference, desktop EXE build and L2-L4 not run because this is a standalone source migration, not hardware deployment or cloud acceptance.
- Final source/diff/secret review and branch publication recorded below.

## Commit intent
feat(strokereview): import image-to-stroke review workflow

## Review boundary
PR targets the committed source branch target/localization-lock-state-machine to avoid mixing its pre-existing commits into this migration. No merge is performed. Another worker may later change README/log; reconcile additive documentation during review. Full robot orchestration and paper-to-arm calibration are follow-up work outside this migration.
