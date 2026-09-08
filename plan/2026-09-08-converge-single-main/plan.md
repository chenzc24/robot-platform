# Converge repository to the latest single main branch

- Status: completed
- Responsible: joint
- Highest validation level: L1 (Git and local repository state only)

## Objective

Make `origin/main` the sole active local and remote branch, remove obsolete
worktrees, and leave the primary worktree clean and synchronized. The current
remote deletion of `app/demo.py` is authoritative.

## Initial state and ownership audit

- Local `main` is at `791e27a` and is 30 commits behind `origin/main` at
  `e748c4a`.
- The primary worktree has user/editor settings, a 15% to 60% drawing-speed
  edit in the now-removed `app/demo.py`, one log addition, one unrelated SVG,
  and four untracked diagnosis/planning directories.
- `target/arm-fault-foundation` contains one unique, unmerged commit and an open
  draft PR. `target/deploy-baseline-devices-20260908` contains one unique,
  unmerged documentation commit. `target/chassis-hold-release-fix` is already
  fully merged but is the current base of that draft PR.
- The merged `target/localized-baseline` branch was deleted concurrently during
  this audit; its clean worktree is detached at the PR #17 merge commit.
- No staged changes or stashes exist. No hardware connection or motion is in
  scope.

## Editable scope

- Git refs and worktree registrations in this repository.
- `plan/2026-09-08-converge-single-main/plan.md`.
- Append-only `plan/log.md` entry for the completed cleanup.
- A repository-external backup directory under `E:\Device Network-backups`.

## Read-only and protected scope

- `ESP32/`, `Camera/`, and `Robot Arm_Claws/` raw-resource archives.
- Device files, credentials, local device configuration and hardware state.
- The content of unique branch commits and pre-existing dirty files, except for
  copying them into the external recovery backup before cleanup.

## Intended procedure

1. Create a Git bundle containing all current refs and copy every dirty file to
   a dated repository-external backup.
2. Close the obsolete draft PR, remove auxiliary worktrees, and delete all
   target branches locally and remotely.
3. restore the primary worktree exactly to `origin/main`, then add only this
   factual cleanup plan/log record.
4. Run repository-appropriate L1 checks, `git diff --check`, and final branch,
   worktree, remote-ref and synchronization audits.
5. Commit and push the cleanup record directly to `main`.

## Risk and recovery

- Branch deletion is destructive to active refs, so all refs are preserved in
  a Git bundle before deletion.
- Dirty files are copied individually to the external backup before the primary
  worktree is restored. The deployment worktree's settings copy is backed up
  separately.
- No unique branch change is merged implicitly. Recovery is possible from the
  bundle without relying on reflogs.

## Validation plan

- Confirm the bundle lists the preserved branch tips.
- Confirm copied dirty files exist in the external backup with matching hashes.
- Confirm only `main` exists locally and remotely, only the primary worktree is
  registered, and `main` equals `origin/main` after push.
- Run relevant local tests selected after reviewing the final `origin/main`
  project entry points.
- Run `git diff --check` and `git status --short --branch`.

## Actual results

- Created and verified
  `E:\Device Network-backups\2026-09-08-single-main-precleanup\repository-all-refs.bundle`.
  It contains the pre-cleanup `main` plus all three target branch tips and the
  complete reachable history. Every pre-existing dirty file was copied with
  matching SHA-256 content before cleanup.
- Closed obsolete draft PR #2. Removed all auxiliary Git worktree registrations
  and deleted all three remaining target branches locally and from `origin`.
- Fast-forwarded local `main` by 30 commits from `791e27a` to the authoritative
  `origin/main` merge commit `e748c4a`. This removed `app/demo.py` and its local
  60% speed experiment as intended.
- Moved the five pre-existing untracked artifact/plan paths into the recovery
  backup rather than deleting them. Restored the dirty editor settings and
  shared log to committed state before the fast-forward.
- The clean detached Baseline and arm-fault worktree directories were removed.
  Git also unregistered the deployment worktree, but Windows reported that its
  physical directory `E:\Device Network-deploy-baseline` was in use and could
  not delete it. It is now an unregistered ordinary directory and is not a Git
  worktree or branch.
- L1 passed: 369 tests across app (7), console (153), dev (28), ESP32 (76),
  MaixCam (58), protocol (28), and robot-arm (19). Root-level unittest discovery
  found zero because this repository requires per-subdirectory discovery.
- No hardware connection, deployment, configuration write, service action or
  motion occurred.
- Final Git diff/status, remote-head, worktree and synchronization checks are
  performed immediately before and after the cleanup-record commit.

## Commit intent

Commit and push only this plan plus its factual `plan/log.md` entry on `main`.
