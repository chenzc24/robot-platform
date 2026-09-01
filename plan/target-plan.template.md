# Destination Name

- Status:`planned | in-progress | blocked | completed`
- Responsible:`<human / agent / joint>`
- Highest validation level:`L0 | L1 | L2 | L3 | L4`

## Objective

Describe a specific, independent acceptance result.

## Initial state of the workspace

Records `git status --short --branch` Output:

```text
<status>
```

If you have a non-dirty file, you can record where you belong and why it's safe to continue working.

## Modifyable File

- `<paths editable by this goal>`

## Read-only files and directories

- `<paths that may be inspected but not modified>`

## Shared Dependencies

- `<protocols, configuration, generated artifacts, documents, or architecture decisions>`

## Risk and safety door

- Risk: `<software, network, firmware, device configuration, or real-motion risk>`
- Hardware: `<none / ESP32 / MaixCam / TCP232 / robot arm / full system>`
- User operations: `<connections, BOOT/RST, configuration, teaching, on-site supervision, and so on>`
- Backup and recovery: `<content to back up and recovery path>`
- Motion gate: `<not applicable, or conditions that must be confirmed before L3/L4>`

## Expected work

1. `<step>`
2. `<step>`
3. `<step>`

## Validation

- `git diff --check`
- `git status --short --branch`
- `<minimum deterministic checks for affected behavior and direct dependencies>`

Description of how the selected validation covers current impacts and risks. When L2, L3 or L4 is required, list the device state, parameters, expected results and cessation conditions.

## Actual results

- `<actual change result>`
- `<validation actually performed>`
- `<checks not run and why>`

## Outstanding matters

- `<remaining risk, blocker, or follow-up goal; write "none" if empty>`

## Experience signal (for manual review)

Recording repeated failures, rules overturned by facts, verification gaps or patterns that may be reused... routine work left blank;

## Intent to submit

```text
<commit message>
```
