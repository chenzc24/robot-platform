# Control Console UI Design

- Status: `completed`
- Responsible: `agent`, with user review of the proposed layout and controls
- Highest validation level: `L0`

## Objective

Define a complete, implementation-ready desktop control-console layout for video, direct ESP32 chassis control, MaixCam-routed robot-arm control, command lifecycle, diagnostics, and fault handling without changing runtime ownership or enabling real motion.

## Initial state of the workspace

The goal starts from the clean, synchronized offline integration candidate:

```text
## target/offline-runtime-integration...origin/target/offline-runtime-integration
```

Work continues in the isolated worktree `E:\Device Network - control-console-ui-design` on `target/control-console-ui-design`. The primary worktree and its user-owned `.vscode/settings.json` remain outside this goal and read-only.

## Modifiable files

- `README.md`
- `docs/overall-plan.md`
- `docs/console/control-console-ui.md`
- `plan/2026-09-01-control-console-ui-design/plan.md`
- `plan/log.md`

## Read-only files and directories

- `protocol/`
- `src/`
- `tests/`
- `tools/`
- `config/`
- `ESP32/`
- `Camera/`
- `Robot Arm_Claws/`
- all device filesystems and local credentials

## Shared dependencies

- Direct computer-to-ESP32 RCP/TCP v2 session and its default-deny safety model.
- Computer-to-MaixCam NDJSON arm session and RPA2 arm lifecycle.
- MaixCam RTSP/H.264 video relayed locally through FFmpeg and MediaMTX.
- Independent video, chassis, and arm links; a healthy link never proves physical readiness.
- Lifecycle states `RECEIVED`, `ACCEPTED`, `RUNNING`, `DONE`, `REJECTED`, `FAULT`, and `UNKNOWN`.
- Current `DONE` evidence does not yet prove measured chassis or arm terminal state.

## Risk and safety gate

- Risk: documentation could accidentally imply deployment, physical completion feedback, or safe motion that has not been validated.
- Hardware: none.
- User operations: review the information hierarchy, control density, terminology, and intended operator workflow.
- Backup and recovery: Git records all documentation changes; no device or configuration recovery is required.
- Motion gate: not applicable. The design keeps motion controls locked until separate L2/L3 acceptance and labels the UI stop as a software stop rather than a physical emergency stop.

## Expected work

1. Define the desktop window structure, responsive behavior, visual hierarchy, and modern restrained style.
2. Specify video, chassis, robot-arm, fault, command, connection, and configuration controls with their enablement gates.
3. Define the UI application boundary, worker/session model, state store, event journal, simulator mode, and binding to existing console interfaces.
4. Define normal debugging workflows, failure behavior, acceptance criteria, and phased implementation.
5. Produce an in-conversation layout mockup and link the design from project entry points.

## Validation

- `git diff --check`
- `git status --short --branch`
- verify all modified Markdown remains English-only
- verify all relative Markdown links resolve
- inspect the complete diff for secrets, unsupported hardware claims, and architecture-boundary changes
- render and inspect the proposed layout at desktop and narrow widths

L0 is sufficient because this goal changes design documentation only. It does not execute code, open a device connection, deploy source, or produce motion.

## Actual results

- Added an implementation-ready English design for the desktop layout, video and future overlay pipeline, independent chassis and arm controls, command journal, persistent fault center, safety gates, worker/session boundary, current-interface mapping, phased implementation, and acceptance criteria.
- Added a responsive interactive layout mockup and inspected its desktop and narrow presentations. Simulator/hardware state, overlay visibility, and arm control tabs are interactive in the preview.
- Linked the design from the repository README and overall plan without changing the frozen runtime topology or any protocol.
- L0 validation passed: workspace policy validation reported no errors, changed Markdown contains no CJK text, links resolve through the workspace validator, and Git diff formatting is clean.
- No source code, protocol, configuration, credential, raw resource, device, network session, or hardware state changed.

## Outstanding matters

- User review is required before the layout becomes the UI implementation baseline.
- PySide6/PyAV selection and implementation belong to a follow-up L1 goal.

## Experience signal (for manual review)


## Intent to submit

```text
docs: define unified control console UI
```
