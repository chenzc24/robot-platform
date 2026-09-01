# Target plan catalogue

`plan/` Preservation of development intent and facts to preserve history, to allow artificial sharing of target boundaries with Agent, document ownership, validation methods and real completion status. It's not a substitute for GitHub Issues, or Git.

## Working closed circle

```text
Defining objectives
Check Git's status and data protection
Create Target Scheme
It's done.
Press L0-L4 to verify
Update the fact log
Review, Submission and Transmission
```

## Target plan

Use of planned tasks:

```text
plan/<YYYY-MM-DD-goal-slug>/plan.md
```

From `plan/target-plan.template.md` Copy structure. Target plan includes at least:

- Status, Target and Workspace Initial Status.
- Can modify files, read-only files and share dependencies.
- Expected work and risks
- Highest level of validation and certainty check.
- Do you need device, user operations and field movement confirmation.
- Actual results, residual risk and submission intent.

A target should respond to the results of a work that can be independently verified, such as the ESP32 Wireless Deployment Channel, not a document or a vague phase.

## Dirty work area

A dirty work area does not automatically prevent unrelated targets.

- Failure to submit documents is irrelevant to the current target.
- No overlap with the modified scope of the current objective.
- Without changing the shared contract on which the current target depends.
- The target plan records the judgement to continue.

If the attribution of the document is not clear, the overlap or the sharing contract may be affected, the editing should be stopped and coordination requested.

## Validation Level

- L0: Document and static configuration.
- L1: Local code, protocol and simulator.
- L2: Connect the real machine without moving.
- L3: Low-speed real motion on a single device must be confirmed on site.
- L4: Multi-device joint mission, confirmed on site.

The plan should select the level to cover the highest risk.

## Maintain Log

`plan/log.md` Recording of accepted project maintenance facts. Each record includes:

- Dates and objectives
- Modify the area.
- Actual validation and ranking
- Whether to connect or drive hardware ...
- Submission status.
- Failure to address or follow up

The plan describes pre-work intentions, post-work facts, Git records actual file status.

## Schedule Archive

- In progress, blocked or failed plans remain in place.
- Mark in completion schedule status `completed`, does not require immediate deletion.
- You can move a completed schedule to a planned number of impact browsing `plan/archive/<year>/`, while retaining `plan/log.md` Index.
- A plan that may contain a reusable memory signal cannot be deleted until the user decides whether to refine it.
