# Robot Platform Agent Working Rules

This repository uses an agent-assisted workflow of goal planning, bounded implementation, risk-based validation, factual logging, and commit/push. Treat it as an engineering project that controls real moving hardware, not as a software-only sandbox.

## 1. Project Entry Points

Read these files in order before starting work:

1. `README.md`
2. `docs/overall-plan.md`
3. `plan/README.md`
4. The design, protocol, and deployment documents for the affected subsystem

Baseline device responsibilities:

- ESP32-S3: receives production chassis commands directly from the computer over the trusted LAN TCP service and owns chassis motion, CAN, motors, sensors, heartbeat stop, and low-level safety. WebREPL remains development and maintenance only.
- MaixCam: owns vision capture, video, the computer-facing robot-arm endpoint, command routing to the robot arm, and arm/video status.
- Robot arm LAN1: controlled by MaixCam through UART/TCP232.
- Robot arm LAN2: used by the computer for maintenance, teaching, deployment, and fault diagnosis.
- Computer: owns VS Code development, deployment, vision inference, the unified console, logging, and high-level task orchestration. During normal operation it communicates directly with ESP32 for chassis control and with MaixCam for video and robot-arm tasks.

Update the overall plan and obtain user confirmation before changing these boundaries.

## 2. Before Starting a Goal

1. Run `git status --short --branch` at the repository root.
2. Audit every uncommitted path and distinguish current-goal work, user changes, other collaborator changes, and historical leftovers.
3. Stop and request coordination if a dirty file overlaps the current ownership scope, has unclear ownership, or changes a shared contract required by the goal.
4. Unrelated dirty files do not need to be cleaned, but they must be noted in the goal plan and must not be modified or staged.
5. Define the goal, risk level, editable files, read-only files, shared dependencies, validation scope, and commit intent.

Create `plan/<YYYY-MM-DD-goal-slug>/plan.md` before editing when a goal:

- changes runtime code, device configuration, a protocol, deployment tooling, or VS Code automation;
- changes the overall architecture, a safety rule, or a cross-device contract;
- requires connecting to, writing to, flashing, or moving real hardware; or
- spans multiple files or subsystems.

A typo, link, or formatting fix in one file that does not change behavior may omit a separate goal directory. It still requires a clean workspace audit, diff validation, and a `plan/log.md` entry if committed.

## 3. File Ownership and Protected Scope

Every goal plan must declare:

- files or directories that may be modified;
- files or directories that may be inspected but not modified; and
- shared contracts, generated artifacts, configuration, or design decisions on which it depends.

Fixed protection rules:

- `ESP32/`, `Camera/`, and `Robot Arm_Claws/` are local raw-resource archives. They are read-only and excluded from Git.
- `tmp/` is for temporary document inspection and is not a product-code source.
- A device filesystem must never be the only source of code. Recover every valid device-side change into version-controlled local source.
- Do not edit outside the declared goal scope. Update the plan before expanding scope.
- Never overwrite, clean, reset, or commit uncommitted work owned by the user or another collaborator.

## 4. Secrets and Local Configuration

Never commit:

- phone hotspot names or passwords;
- SSH, WebREPL, Tailscale, or device login credentials;
- private keys, access tokens, or real secret configuration; or
- terminal output, logs, or device backups that contain secrets.

Use secret-free templates such as `.env.example` and `*.example.yaml`. Store real values in `.env` or `*.local.yaml`, and keep those paths excluded by `.gitignore`. Avoid printing credentials during diagnostics.

## 5. Implementation Discipline

- Keep each goal bounded; do not mix unrelated cleanup or refactoring into it.
- Prefer small, reviewable commits.
- The local repository is the source of truth; deploying to a device is a release action.
- A shared-protocol change requires coordinated review of `protocol/`, `src/esp32/`, `src/maixcam/`, `src/console/`, simulators, test vectors, and related documentation. Explain any unaffected area in the plan.
- Do not scatter hard-coded network addresses, serial ports, TCP232 settings, or robot-arm parameters. Use a configuration model with local overrides.
- Update the goal plan before continuing when new risks, dependencies, or scope appear.
- Add tests only when behavior changes, regression protection is needed, or a shared contract requires them. Do not duplicate implementation logic merely for formal completeness.
- Start validation with the smallest deterministic check and expand it as risk or impact increases.

## 6. Hardware Write and Motion Safety Gates

### 6.1 Before Writing to a Device

- Confirm the device model, connection method, target port, and power state.
- Read current state and back up recoverable content before flashing firmware, erasing a filesystem, or overwriting device configuration.
- Define a recovery path, including USB, BOOT/RST, known-good firmware, and device-file backups.
- Do not change robot-arm IP settings, TCP232 mode, chassis bus parameters, safety limits, or taught points without explicit user authorization.

### 6.2 Before Producing Motion

Before L3 or L4 validation, obtain explicit confirmation for the current test that:

- a person is present and can operate the physical emergency stop;
- the area around the robot arm and chassis is clear of people and obstacles;
- the chassis is raised, restrained, or inside the agreed safe area;
- the robot arm uses a confirmed safe pose, workspace, low speed, and load; and
- the expected motion, stop conditions, and failure response have been explained.

Never:

- run unattended real-motion tests;
- rely on Wi-Fi, SSH, WebREPL, Tailscale, or a computer software stop as the only protection;
- increase speed, workspace, or gripping force, or bypass an interlock merely to pass a test; or
- move the robot arm before the chassis has confirmed stop, or allow high-speed chassis motion before the arm has returned to its safe pose.

## 7. Validation Levels

Select the level that covers the highest risk of the goal:

| Level | Scope | Typical checks |
|---|---|---|
| L0 | Documentation and static configuration | Formatting, links, schema validation, `git diff --check` |
| L1 | Local software and simulators | Unit tests, protocol vectors, simulated devices, type and syntax checks |
| L2 | Real-device connection without motion | Discovery, SSH, WebREPL, serial, TCP connection, status queries |
| L3 | Controlled low-speed motion of one device | Chassis or arm motion, command timeout stop, emergency-stop validation |
| L4 | Coordinated multi-device task | Chassis-vision-arm interlocks, link loss, and fault recovery |

Requirements:

- L0 and L1 may run automatically without hardware.
- L2 must not imply motion. If connecting the target can cause motion, treat it as L3.
- L3 and L4 require the manual safety gate above.
- Never record unperformed validation as passed. Record it as not run, with the reason and residual risk.
- Every goal must run at least `git diff --check` and `git status --short --branch`.

## 8. Completing a Goal

Complete these steps in order:

1. Run the planned validation appropriate to the risk.
2. Review the full diff and confirm that no secret, device backup, or raw resource enters Git.
3. Record actual results and unresolved items in the goal plan.
4. Add a factual `plan/log.md` entry covering the goal, modified scope, validation, hardware state, and commit status.
5. Stage only files declared in the plan.
6. Commit and push with the stated intent.
7. Confirm that the local branch and its remote are synchronized.

Current branch policy:

- A single-person, low-risk goal with clear boundaries may commit directly to `main`.
- Use a `target/<slug>` branch and pull request for cross-subsystem, high-risk, review-dependent, or parallel work.
- Do not combine unrelated goals in one commit.

## 9. Plans, Logs, Git, and Lessons

- A plan records intent, scope, and validation commitments before changes.
- A log records facts after work is performed.
- Git records the actual version state.
- A lesson is a reusable conclusion derived from multiple facts.

This repository does not currently use a permanent lessons directory. Agents must not automatically claim that one task produced a reusable lesson. A goal may mark a "lesson signal" when a failure repeats, a rule is disproved, a validation gap appears, or a safety pattern is transferable. Create a lesson document only when the user explicitly requests it.
