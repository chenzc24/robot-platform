# Consolidate the validated drawing lineage into main

- Status: completed; PR #3 merged into main, local main synchronized
- Owner: Codex, single-agent integration
- Validation ceiling: L1; no hardware connections, deployment or motion
- Authorization: user approved consolidation after the branch review.

## Objective and Git intent

Integrate the existing 15-commit lineage from main f7527c9 through drawing
838f61b, with bounded test-isolation and status-documentation corrections.
Continue on target/pc-json-drawing-demo; retarget existing PR #3 to main,
update its expanded scope, and merge with a merge commit preserving ancestry.
Synchronize local main and leave the primary checkout on main if dirty work can
be preserved without stashing or rewriting it. Do not force-push any branch.

Keep draft PR #2 / target/arm-fault-foundation separate: its error protocol and
XYZ preflight still require coordinated endpoint validation. Preserve its
worktree and all historical branch references; branch deletion is deferred.
Do not merge the five historical divergent branches identified in the review.

## Initial workspace and ownership

Current branch: target/pc-json-drawing-demo, 838f61b, synchronized with origin.
main is f7527c9 and is an ancestor. Existing dirty paths are read-only:

- .vscode/settings.json: user editor buttons.
- app/demo.py: user changed DRAW_SPEED_PCT from 15 to 60. Preserve bytes; do not
  include this speed change in the integration commit or run a hardware test.
- plan/log.md: prior 19-line XYZ diagnosis. Preserve it; append and stage only
  this goal's section under the user's earlier append authorization.
- Untracked plan/2026-09-03-arm-xyz-singularity-diagnosis/,
  plan/2026-09-03-arm-yz-drawing-review/ and
  plan/2026-09-03-video-stream-diagnosis/: other diagnostic work, untouched.

The fault-foundation worktree is clean at 32dad12. Local ignored operator
configurations and dataset are not test fixtures, source changes or Git inputs.
Protected-file hashes were captured before editing for final verification.

## Editable scope

- This plan and only the new goal section in plan/log.md.
- tests/app/test_demo.py and tests/maixcam/test_arm_command_server_config.py.
- tests/esp32/test_chassis_runtime_factory.py: its L2 factory test also depends
  on ignored device_config; inject synthetic config and no credential.
- README.md, docs/overall-plan.md, docs/runtime/README.md,
  docs/deployment/README.md, src/robot_arm/runtime/README.md and app/README.md:
  synchronize dated evidence/status, not architecture or safety boundaries.
- PR #3 metadata and its merge into main; local/remote Git synchronization.

## Read-only dependencies and risks

All runtime code, protocol, device configuration, deployment manifests, dataset,
raw archives, existing plans/log entries, services and other worktrees remain
read-only. Production defaults remain 15/5/5 percent. No physical completion,
new speed, startup reliability or coordinated L4 acceptance is inferred from
unit tests, a Git merge, prior status samples or a completed drawing.

Avoid overwriting local changes when main advances. Verify branch ancestry and
remote head again immediately before merge; stop if concurrent changes alter
the reviewed scope. Use the PR merge as the authoritative publication record.

## Work and validation

1. Make the drawing geometry test pass explicit speeds; retain header-default
   propagation tests. Isolate MaixCam template imports from local overrides and
   separately test override precedence with a synthetic module.
2. Correct stale maturity claims using dated deployment, feedback and drawing
   evidence; distinguish default-deny source from attended YOLO configuration.
3. Run local app, console, arm, MaixCam, protocol, ESP32 and development tests,
   plus chassis JavaScript regressions. Check committed/default drawing values
   in memory as well as the unchanged user-customized header. Check local
   configuration independence without copying secrets or changing their files.
4. Review complete scoped diff, documentation links, git diff --check and status.
   Record actual results and limitations before selective staging and commit.
5. Push, verify PR scope/mergeability, merge without bypassing protection, fetch,
   verify main contains the reviewed lineage and matches origin/main, and check
   that all pre-existing local work remains intact.

L2/L3/L4 are not run: this is repository integration, not device release.

## Actual results

- Fixed drawing geometry-test speed isolation without changing app/demo.py.
  Header propagation tests still use the actual defaults and synthetic edits.
- Isolated the MaixCam default template; added synthetic override-precedence
  coverage. Reproduced the ESP32 missing-device_config failure, then isolated
  its L2 factory fixture and no-credential input. No runtime behavior changed.
- Updated current evidence in six entry documents; linked dated deployment and
  drawing records and clarified API completion, unsupported cancellation,
  manual console/script handoff and remaining L4/recovery limitations.
- Passed 301 Python tests: app 19, console 99, arm 18, MaixCam 57, protocol 28,
  ESP32 55 and development tools 25. Chassis JavaScript tests: 13/13 passed.
- Additional app reruns passed 19/19 with the committed 15/5/5 source loaded
  only in memory, and 19/19 with synthetic 100/90/80 header defaults. These are
  fake-IO tests, not high-speed hardware validation; the user's 60% is unchanged.
- Configuration-isolated reruns passed ESP32 55/55 and MaixCam 57/57 with local
  device/arm override modules blocked. No configuration file was edited/copied.
- Scoped Markdown links and git diff --check passed; scoped diff reviewed.
  No new runtime source, protocol, secrets, raw archive or dataset is staged.
- L2/L3/L4 not run. Existing services, controller, session owners and physical
  state were not queried or changed. No higher-speed motion acceptance claimed.
- Correction commit 153b6e2 was selectively staged, committed and pushed. PR #3
  was retargeted from target/chassis-hold-release-fix to main with the expanded
  16-commit scope, validation and exclusions recorded in its description.
- GitHub merged PR #3 at 2026-09-03 08:09:23 UTC as 5394fbc, preserving ancestry.
  The fetched merged tree exactly matches tested head 153b6e2. No branch
  protection was bypassed; the PR had no configured status-check results.
- Local main advanced from ancestor f7527c9 to origin/main; the primary checkout
  switched to main without stashing, overwriting or committing user work.
  main/origin divergence was 0/0 immediately after merge.
- Post-merge hashes of user speed/editor files and four diagnostic files match
  the initial audit. The unstaged XYZ log hunk is unchanged. Draft PR #2 remains
  open, its worktree clean at 32dad12 and its unique commit absent from main.
- All branch references are retained. This final documentation-only outcome
  record is committed/pushed on main; Git records its resulting commit ID.
