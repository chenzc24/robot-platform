# Arm fault diagnosis and explicit recovery foundation

- Status: completed (local implementation and L0/L1 scope; device integration pending)
- Owner: Codex, single-agent implementation
- Validation: L0/L1 only; no hardware connection, writes, clearing, or motion
- Risk: safety-related, cross-subsystem arm protocol change; review before deployment

## Objective

Preserve structured controller/preflight errors through the existing arm route,
preflight user-coordinate XYZ translations, and expose separate capabilities,
fault queries, controller alarm clearing, and service recovery. No automatic
enable, resume, replay, escape motion, or controller-mode/network change.
Trajectory planning and automatic avoidance are explicitly future work.

## Workspace audit and isolation

Original checkout: E:/Device Network, target/chassis-hold-release-fix, c313e88.
Its dirty .vscode/settings.json is user configuration; plan/log.md and untracked
plan/2026-09-03-arm-xyz-singularity-diagnosis/ are a separate diagnostic task.
All are read-only and excluded from this goal's edits and commits. To avoid the
shared-log overlap, implementation uses a clean worktree at
E:/Device Network/.tools/worktrees/arm-fault-foundation on
target/arm-fault-foundation, based on c313e88. No original work is moved/stashed.

## Editable scope (isolated worktree only)

- This plan; plan/log.md in this clean worktree only.
- src/robot_arm/runtime/ (fault module, motion adapter/service, entry and README).
- protocol/motion_link.py, protocol/motion-link-v1.md and related test vectors.
- src/maixcam/arm/arm_motion_gateway.py and command_service.py.
- src/console/maixcam_arm_client.py, runtime_core.py, new arm fault parsing module.
- Arm-specific portions of src/console/web_console/{runtime.py,server.py,static/}.
- tools/robot_arm/build_dobotstudio_project.py.
- tests/{robot_arm,maixcam,console,protocol}/ for affected behavior and offline integration.
- docs/robot-arm/fault-management.md; relevant arm/console deployment and API docs.

## Read-only dependencies

All original-checkout files, raw resource archives, extracted vendor package,
ESP32 sources, chassis code/behavior, local configurations/secrets, unrelated
plans, UI fallback, deployment services, existing device files and running UI.
The shared envelope and 512-byte RPA2 framing remain; ESP32 does not consume the
arm protocol. Review its separation, but do not modify chassis contracts.
Generated build/ output is ignored, never the source of truth.

## Implementation and compatibility

1. Audit controller Python whitelist, keeping it distinct from native TCP SDK.
2. Add bounded structured fault evidence, native numeric results, source API,
   local timestamps and explicit truncation. Do not mislabel unknown codes.
3. Preflight XYZ in the same user/tool frame, preserving orientation; reject
   unavailable/invalid feedback or nonzero/unknown check results without motion.
4. Add capability-gated fault query/clear/recover contracts with no hidden
   control-mode switch, enable or resume. Unsupported vendor operations must
   remain honestly unsupported on the current controller project.
5. Propagate errors and timestamps end-to-end; separate UI ACK from clear and
   recovery; preserve history and UNKNOWN outcomes. Emit lifecycle replies before
   synchronous motion, but do not claim concurrent diagnostics while it blocks.
6. Update builder, docs, simulator tests and protocol vectors.

## Validation commitments

- Small deterministic adapter tests first; controller and gateway protocol tests.
- Unknown/invalid native responses fail closed; frame-size, ASCII, duplicates,
   timestamp and truncation tests. Check coordinate frame, nonzero User/Tool,
   all rejection paths, and never execute a rejected XYZ translation.
- Clear requires explicit request plus verified capability/state; check before
   and after; preserve raw evidence and reject unsafe/unknown conditions.
- Recovery does not clear device alarms, replay motion, erase history, or
   convert an unresolved task into DONE. No retries after write/timeout.
- Offline PC/gateway/controller roundtrip, fault rendering and HTTP validation.
- Builder standalone compile; relevant full local tests and JS syntax/tests.
- git diff --check, full scoped diff/secret review, git status --short --branch.
- L2/L3/L4 not run: actual alarm API support and machine behavior need a later
   approved device session with backups and physical safety gate.

## Commit intent

feat(arm): add structured fault diagnostics and explicit recovery contracts

Commit/push only scoped files; open a review PR with the correct dependency
base after checking upstream branch state. Do not merge or deploy. Preserve
the original checkout and its uncommitted diagnostic records.

## Actual results / remaining work

- Added fault-v1 capability/query/clear/recover contracts, bounded raw evidence,
  native numeric preflight codes, source API and controller/PC timestamps.
- XYZ uses fresh GetPose(user, tool) and matching CheckMovL options before
  RelMovLUser. Invalid or ambiguous check results fail closed. Native execution
  errors latch service fault; preflight rejections do not execute motion.
- Controller ACK/RUNNING now flush before the native blocking call. Requests
  buffered behind another call retain their arrival time and can expire.
- Clear and service recovery are separate; both require explicit confirmation
  and a verified adapter with stationary, empty-queue, no-estop checks. Clear
  verifies after-state and preserves before/after evidence; recovery never
  resumes, enables, replays, deletes history, or resets sequence deduplication.
- UI adds independent query/clear/recovery controls, capability gating, raw
  evidence, stale indication and configured persistent journal evidence. ACK
  remains acknowledgement only. Recovery in progress rejects new motion.
- Controller package audit confirms no exported GetErrorID/RobotMode/ClearError
  in the normal Python project whitelist. A binary symbol alone is not a supported
  callable. Actual controller query/clear and verified service recovery remain
  unsupported in the current deployed-style adapter, not falsely advertised.
- L1 passed: 33 robot-arm + 56 MaixCam + 109 console + 29 protocol tests = 227;
  16 Node tests (fault controls and unchanged chassis input regressions).
- Additional development-tool regression suite: 25/25 passed.
- Source syntax: 43 Python files including generated disabled/YOLO projects;
  JS syntax and both four-file controller project builds passed.
- Expanded unrelated ESP32 suite: 54/55 passed, one existing missing
  device_config / l3_device_config_missing failure in the clean worktree.
  Workspace validator reports existing non-ASCII lines 471/487 in legacy
  src/console/ui/views.py. git diff confirms these areas unchanged from c313e88;
  no unrelated fix or local secret/config copy was performed.
- Full scoped diff reviewed; no raw resources, device backups or credentials
  added. git diff --check passed (existing CRLF normalization warnings only).
- L2/L3/L4 and browser visual/device acceptance not run. No device connection,
  clear, restart, deployment, mode change, enable or movement was performed.
- Build outputs are ignored. The original checkout and all three dirty paths
  remain untouched. Original diagnostic notes were inspected but not committed.
- Git plan: commit/push this worktree only. origin/main is still f7527c9, so the
  review PR is stacked on target/chassis-hold-release-fix (c313e88), excluding
  its older unmerged changes from this review. No merge is authorized.

## Remaining integration gates

1. Verify actual CheckMovL/CheckMovJ return containers and nonzero User/Tool
   semantics in a separately approved non-motion session.
2. Select and prove a supported controller alarm/state/clear channel without
   silently changing the current ownership or TCP232 mode. Update architecture
   and obtain confirmation first if such a change is required.
3. Deploy matching controller/MaixCam/protocol/PC versions as a stopped-task
   release, with known-good backups; run L2 and then attended L3.
4. Continuous singularity margins, curve planning and automatic adjustment are
   not part of this foundation; CheckOdd/MovS adoption needs capability review.
