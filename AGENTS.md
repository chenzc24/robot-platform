# Robot Platform Agent Rules

Treat this repository as software that controls real moving hardware. Keep the
workflow small, preserve user work, and validate in proportion to risk.

## Start Here

Before changing the repository:

1. Read `README.md`, `docs/overall-plan.md`, and the affected subsystem docs.
2. Run `git status --short --branch` and identify unrelated user changes.
3. State the intended scope, dependencies, risk and validation in the task
   conversation. A repository plan or work log is not required.

`plan/` is an ignored local scratch area. Notes there are optional, are not a
source of truth, and must not be required for implementation, review or commit.
Git and current subsystem documentation record durable project state.

## Architecture

- ESP32-S3 owns chassis motion, CAN, motors, sensors, connection-health stop
  and low-level safety. Production chassis commands arrive directly from the
  computer over the controlled-LAN TCP service. WebREPL is maintenance-only.
- MaixCam owns video capture and the computer-facing robot-arm gateway.
- Robot-arm LAN1 is controlled through MaixCam and TCP232. LAN2 is for
  maintenance, deployment, teaching and fault diagnosis.
- The computer owns development, deployment, vision inference, logging and
  high-level orchestration.

Update `docs/overall-plan.md` and obtain user confirmation before changing
these device boundaries.

## Ownership and Protected Scope

- Preserve unrelated dirty files and never stage, overwrite, reset or clean
  user or collaborator work.
- `ESP32/`, `Camera/`, and `Robot Arm_Claws/` are ignored read-only raw-resource
  archives.
- `tmp/` is temporary inspection output, not product source.
- A device filesystem must never be the only copy of valid source. Recover
  device-side changes into version-controlled source.
- Keep changes bounded. Expand scope only when the task actually requires it.

## Secrets and Local Configuration

Never commit passwords, private keys, tokens, real device credentials, private
network configuration, or device backups containing secrets. Use commit-safe
templates and ignored `.env`, `*.local.yaml`, `*.local.json`, or device-local
configuration. Avoid printing secrets during diagnostics.

## Implementation and Tests

- Prefer small, reviewable changes. The repository is the source of truth;
  deployment is a separate device action.
- Shared-protocol changes must review the affected protocol, device runtime,
  PC client, simulator/test vectors and current documentation. Do not preserve
  tests solely for superseded protocol generations.
- Centralize network addresses, ports and physical parameters in configuration.
- Add or retain tests when they protect current behavior, regression-prone
  logic, safety behavior or a shared contract. Remove duplicate and historical
  tests once their runtime is no longer production-supported.
- Do not over-test. Start with the smallest deterministic check that exercises
  the changed behavior. Do not run the full suite by default for a local or
  low-risk change; expand only when the change crosses a shared contract, the
  focused check fails, the affected surface is broad, or the user requests it.
- Do not repeat equivalent checks at unit, simulator and integration levels
  without a concrete regression risk. One clear test is preferable to several
  ceremonial tests of the same behavior.

## Hardware Writes

Before writing a device, confirm its identity, connection method, target and
power state. Back up recoverable overwritten content and identify a recovery
path. Do not change robot-arm IP settings, TCP232 mode, chassis bus parameters,
safety limits or taught points without explicit user authorization.

## Real Motion

Use a lean safety process. Do not add speculative software gates, repeated
checklists or confirmation prompts when the risk is already covered by the
site's physical safeguards and the operator's stated setup. Non-motion status,
connectivity and simulation work must not be blocked by motion-only checks.

Before a real chassis or arm movement, obtain one explicit confirmation that an
operator can use the physical emergency stop, the area is clear, the chassis is
restrained or in the agreed area, the arm pose/workspace/speed/load are safe,
and the expected movement and stop response are understood. That confirmation
remains valid for an uninterrupted run with the same operator, equipment,
workspace, motion envelope and stop conditions. Do not ask again before every
command, stroke, window or retry unless one of those conditions changes or an
unexpected event occurs.

Once the operator has confirmed the setup and requested execution, use the
shortest direct production path. Do not insert repeated dry-runs, redundant
preflights, polling loops or home cycles unless required by the device protocol,
the current failure state or a changed physical condition.

Never run unattended motion, treat a network/software stop as the only
protection, bypass an interlock to pass a test, move the arm before the chassis
has confirmed stop, or start high-speed chassis motion before the arm is safe.

## Validation

Use the level matching the highest risk:

| Level | Scope | Examples |
|---|---|---|
| L0 | Documentation/configuration | links, schemas, `git diff --check` |
| L1 | Local code/simulation | focused tests, protocol vectors, syntax |
| L2 | Real device without motion | discovery, connection, status |
| L3 | Controlled single-device motion | bounded chassis or arm movement |
| L4 | Coordinated device motion | chassis/vision/arm interlocks |

L3 and L4 require the applicable motion confirmation above. Never report an
unperformed check as passed. Keep validation proportional: for a small code
change, one focused check plus `git diff --check` and a final status review is
normally sufficient.

## Git

Use `main` for bounded single-person work unless the user requests a branch or
the change genuinely needs parallel review. Commit and push when requested or
when completing a clearly authorized repository change; do not mix unrelated
work in one commit. Stage only the files that belong to the task.
