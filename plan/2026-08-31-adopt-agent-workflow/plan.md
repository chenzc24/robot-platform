# Introduction of robot projects into the workflow Nuclear

- Status:`completed`
- Responsible: Agent Implementation, User Decision-Making
- Highest validation level:`L0`

## Objective

Will `agent-workflow-kernel` The plan-implementation-validation-dimension logs-representation of closed loops to this repository, and streamlining and customization of ESP32, MaixCam, robot arm and real motion security.

## Initial state of the workspace

Implementation `git status --short --branch` The results are:

```text
## main...origin/main
```

The work area is clean, and we can start the target.

## Modifyable File

- `AGENTS.md`
- `README.md`
- `plan/README.md`
- `plan/target-plan.template.md`
- `plan/log.md`
- `plan/2026-08-31-adopt-agent-workflow/plan.md`

## Read-only files and directories

- `docs/overall-plan.md`
- `ESP32/`
- `Camera/`
- `Robot Arm_Claws/`
- `tmp/`

The last three device catalogues and the temporary analysis catalogues are all by `.gitignore` Excluded, this objective cannot be modified.

## Shared Dependencies

- `docs/overall-plan.md` It's a frozen device duty, cyber-stamping and safety principles.
- `.gitignore` In information, secret configuration and backup protection.
- Upstream `chenzc24/agent-workflow-kernel` It's a plan. It's a log.

## Expected work

1. Create project specific `AGENTS.md`, preserve the upper core, ownership, validation and submission of discipline.
2. Add robotic hardware security doors, protocol connection rules, secret information protection and rating requirements.
3. Add streamlined target plan statements, templates and maintenance logs.
4. Update the repository README to show how development targets are implemented.
5. Refusal to join the repository of experience; experience distillation is only available when clearly requested by the user.

## Validation

- `git diff --check`
- `git status --short --branch`
- Use `rg` Check plans, logs, check levels, read-only and true motion confirmation rules.
- Use `git check-ignore` The review of three directories is still not being managed.
- Review the pending discrepancies and confirm that only documents containing this plan statement are available.

These checks cover all document behaviour and repository protection rules for this target; This target does not change the running codes, so no device testing or complete testing packages are required.

## Actual results

- Special purpose for robotic projects established `AGENTS.md`, and keep the target range of the upstream core, document ownership, risk verification, fact logs and submission loops.
- We've added data-only protection, secret information protection, device written into recovery requirements and L3/L4 real motion safety doors.
- A statement of the target plan has been established, templates and maintenance logs are maintained; the directory of experience is suspended for decision.
- `git diff --check` Pass.
- `rg` Check the confirmation plan, logs, L0-L4, three directories of information, real movement confirmation and experience trigger rules exist.
- `git check-ignore` Confirm. `ESP32/`, `Camera/`, `Robot Arm_Claws/` and `tmp/` Still neglected.
- No connection, write or drive any real device.

## Outstanding matters

- None. This workflow will be used for the first time in the next target, "VS Code Development Environmental Baseline", to run codes and develop configurations.

## Experience signal (for manual review)

This is just the introduction of the workflow baseline, not the lessons.

## Intent to submit

Submission of information:

```text
docs: adopt robot development workflow kernel
```
