# Main Branch and Worktree Consolidation

- Status: `in-progress`
- Responsible: `joint`
- Highest validation level: `L1`

## Objective

Fast-forward the accepted YOLO arm implementation into `main`, make
`E:\Device Network` the single canonical source worktree, preserve relevant
ignored local deployment artifacts, and remove redundant local worktrees and
branch references without reviving superseded architectures.

## Initial state

- `main` and `origin/main` are at `e07080c`.
- `target/arm-yolo-manual-control` is clean, synchronized, and two commits
  ahead of `main` with no divergence.
- Eleven of twelve worktrees are Git-clean. The primary directory has one
  user-owned modification in `.vscode/settings.json`; it will remain unstaged
  and unchanged.
- The current YOLO worktree contains ignored local configuration, device
  backups, logs, caches, build output, and temporary generated projects.

## Integration decision

Only `target/arm-yolo-manual-control` will be integrated. The following
unmerged branches are retained remotely as historical references and must not
be merged into `main`:

- `target/control-console-ui-convergence`: superseded UI prototype.
- `target/integration-readiness-map`: stale pre-integration snapshot.
- `target/maixcam-esp32-uart-l2`: abandoned UART chassis route.
- `target/motion-services-v1`: superseded service architecture.
- `target/protocol-v1-deployment-workflow`: superseded protocol/deployment
  tooling baseline.

## Editable scope

- Git branch/worktree metadata for this repository.
- This plan and `plan/log.md`.
- Ignored local artifact destinations under the canonical worktree.

## Protected scope

- `.vscode/settings.json` is user-owned and must not be staged, overwritten,
  or discarded.
- Raw resources, secrets, device backups, local configuration, and existing
  logs in `E:\Device Network` must not be overwritten.
- Remote unmerged historical branches must not be deleted.

## Artifact migration

- Copy the active console configuration, ESP32 device configuration, YOLO arm
  build, device backups, logs, and device cache into non-conflicting locations
  in `E:\Device Network`.
- Verify source/destination file counts and SHA-256 content before removing the
  source worktree.
- Do not migrate `.venv`, `.tools`, or temporary document extraction; these are
  reproducible or explicitly temporary.

## Validation

- Fast-forward-only merge and synchronized `origin/main`.
- Focused protocol, robot-arm, MaixCam, console, and development test suites.
- Offscreen console smoke test and Python compilation.
- `git diff --check`, final branch/worktree inventory, and preservation audit.

## Commit intent

```text
docs(plan): prepare main worktree consolidation
docs(plan): record main worktree consolidation
```
