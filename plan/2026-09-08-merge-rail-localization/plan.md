# Merge rail localization and prune merged branches/worktrees

- Status: complete
- Responsible: agent merge and repository hygiene
- Highest validation level: L0

## Objective

Merge clean PR #5 into `main`, advance the primary checkout without losing any
uncommitted user work, remove only branches and worktrees whose commits are
fully contained in `main` and which are not used by an open PR, then record the
actual repository state. No runtime deployment or device operation is included.

## Initial state

- Root checkout: `target/localization-lock-state-machine` at `e5fbdd5`, synced
  with its upstream; PR #5 is open, mergeable and CLEAN against `main`.
- Protected root changes: `.vscode/settings.json`, `app/demo.py`, the existing
  unstaged XYZ section in `plan/log.md`, `pelican-bicycle.svg`, and three
  untracked diagnostic plan directories.
- `arm-fault-foundation` worktree is clean but belongs to open draft PR #2;
  preserve its worktree, head branch and base branch.
- `strokereview-migration` worktree is clean and has no open PR. Remove it only
  after its head is verified as an ancestor of merged `main`.

## Modifiable state and files

- GitHub PR #5 merge state
- primary checkout branch and synchronized `main`
- fully merged local/remote branches not protected by an open PR or worktree
- clean, fully merged `strokereview-migration` worktree registration/directory
- this plan and one appended `plan/log.md` section

## Protected scope

- all existing dirty/untracked root files listed above
- `target/arm-fault-foundation`, its worktree, and its PR #2 base
- any unmerged branch or any branch used by an open PR/worktree
- all runtime/device files and device state

## Procedure and validation

1. Merge PR #5 normally and verify its tested head is contained in merge commit.
2. Switch the primary checkout to `main`, fast-forward from `origin/main`, and
   verify protected changes remain present.
3. Enumerate merged branches after fetch/prune. Remove only branches satisfying
   all cleanup criteria; verify the external worktree's exact resolved path and
   clean state before `git worktree remove`.
4. Run `git worktree prune`, inspect final worktrees/branches/open PRs, verify
   `main` remote divergence is 0/0, and run `git diff --check`.
5. Record facts, stage only this plan and the new log hunk, commit and push main.

## Cleanup recovery

Deleted branch names can be recreated from the merge history/reflog or remote
commit IDs. No branch containing commits absent from `main` may be deleted.

## Actual results

- PR #5 merged normally at 2026-09-08 01:21:15 UTC. Merge commit `383d9c3`
  contains tested head `e5fbdd5`, and their final file trees match.
- Local `main` was aligned to `origin/main` and selected with 0/0 divergence.
  Git initially refused a switch through the older local main because it would
  overwrite the unstaged log hunk; the current target pointer was advanced to
  the identical merge tree, local main was then moved to that tree, and the
  switch completed without overwriting any file.
- Deleted 10 local and 23 remote branch names whose commits are contained in
  main and which are not needed by an open PR or worktree. The merged
  localization head branch was included in that cleanup.
- Preserved `target/chassis-hold-release-fix` because it is the base of open
  draft PR #2 and preserved its `target/arm-fault-foundation` worktree/head.
- Preserved `target/strokereview-migration` and `E:/Device Network-strokereview`:
  during the audit it advanced from `0eec878` to unmerged `403ef7d`, so it no
  longer met the deletion rule. Both retained worktrees are clean.
- Ran worktree pruning; three valid worktrees remain. The protected root edits,
  SVG and diagnostic directories remain present and unstaged. No source edit,
  device connection, deployment, service operation or motion occurred.

## Intent to submit

```text
docs(plan): record rail localization merge and cleanup
```
