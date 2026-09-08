# StrokeReview migration

- Status: completed
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

## Publication and final checks
- Implementation commit `92bfe36` pushed to origin/target/strokereview-migration.
- Initial staged whitespace check reported inherited trailing spaces/EOF blank lines in seven upstream files. The first commit retained these; a follow-up removes them and corrects the validation record. No semantic changes.
- Project-scoped stop command succeeded and released the smoke-test ports.
- Final aggregate diff check is required against base 0eec878, not just the clean working tree.
- Final aggregate `git diff 0eec878 --check` passed after whitespace cleanup.
- Draft review PR: https://github.com/chenzc24/robot-platform/pull/6. No merge performed.

## Main integration

- After localization PR #5 merged, rebased this branch onto `origin/main`
  (`791e27a`). The only conflict was the append-only `plan/log.md`; both the
  localization records and this migration record were retained.
- Rebase changed implementation commit IDs to `35a396b` and `1d3e8b1`; the
  original IDs above remain the historical pre-rebase publication record.
- Revalidation after rebase: aggregate `git diff origin/main...HEAD --check`
  passed. The rebase changed only ancestry and reconciled the factual log, so
  the previously completed L1 application tests remain applicable.
- Publish the rebased branch with force-with-lease, create a new PR against
  `main`, merge it, then remove the merged migration branch and worktree.

## Merge and cleanup outcome

- Rebased branch published with force-with-lease. Replacement PR #7 targeted
  `main`, was cleanly mergeable, and merged as `e36a721`; its remote head branch
  was deleted. Closed PR #6 remains only as historical review metadata.
- Deleted five orphaned remote branches with no associated PR, all superseded
  by later mainline work: `target/control-console-ui-convergence`,
  `target/integration-readiness-map`, `target/maixcam-esp32-uart-l2`,
  `target/motion-services-v1`, and
  `target/protocol-v1-deployment-workflow`.
- Preserved `target/chassis-hold-release-fix` because open draft PR #2 uses it
  as its base. Preserved `target/arm-fault-foundation` and its worktree because
  that PR remains open and unmerged.
- The primary `main` worktree still contains another worker's uncommitted
  `.vscode/settings.json`, `app/demo.py`, `plan/log.md`, SVG and diagnostic plan
  changes. They were not modified or temporarily displaced. Remote `main` is
  updated here; that working tree must fast-forward after its owner finishes or
  commits the overlapping log change.
- After this record is pushed directly to remote `main`, remove the clean
  `E:/Device Network-strokereview` worktree and both local migration/cleanup
  branch names, then prune worktree metadata.
