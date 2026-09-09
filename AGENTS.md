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
- Start with the smallest deterministic validation and expand with risk.

## Hardware Writes

Before writing a device, confirm its identity, connection method, target and
power state. Back up recoverable overwritten content and identify a recovery
path. Do not change robot-arm IP settings, TCP232 mode, chassis bus parameters,
safety limits or taught points without explicit user authorization.

## Real Motion

Before a real chassis or arm movement, obtain explicit confirmation for the
current test that an operator can use the physical emergency stop, the area is
clear, the chassis is restrained or in the agreed area, the arm pose/workspace/
speed/load are safe, and the expected movement and stop response are understood.

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

L3 and L4 require the current-test motion confirmation above. Never report an
unperformed check as passed. For code changes, run at least a focused validation,
`git diff --check`, and a final `git status --short --branch` review.

## Git

Use `main` for bounded single-person work unless the user requests a branch or
the change genuinely needs parallel review. Commit and push when requested or
when completing a clearly authorized repository change; do not mix unrelated
work in one commit. Stage only the files that belong to the task.
