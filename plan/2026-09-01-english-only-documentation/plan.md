# Convert All Repository Documentation to English

- Status: `completed`
- Date: `2026-09-01`
- Branch: `target/english-only-documentation`
- Highest validation level: `L0`

## Goal

Convert every Git-managed Markdown document in the robot-platform repository to English, including entry documents, subsystem documentation, collaboration rules, plan templates, historical goal records, and the factual work log. Preserve technical meaning, commands, paths, identifiers, measurements, safety constraints, validation results, and Git history semantics.

## Initial Workspace State

```text
## target/single-gateway-runtime-deployment...origin/target/single-gateway-runtime-deployment
 M .vscode/settings.json
```

The current architecture branch is synchronized with its remote. `.vscode/settings.json` contains an unrelated user-owned change and remains read-only, unstaged, and uncommitted.

## Editable Scope

- Every Git-managed `*.md` file outside the ignored raw-resource and temporary directories.
- This goal plan and `plan/log.md`.

## Read-only Scope

- `.vscode/settings.json` and all non-Markdown files.
- `src/` program files other than Markdown README files.
- `protocol/` schemas and implementations other than Markdown protocol documentation.
- `tests/`, `tools/`, configuration, device filesystems, backups, caches, and local secrets.
- Ignored raw-resource directories: `ESP32/`, `Camera/`, and `Robot Arm_Claws/`.

## Shared Dependencies

- The single-gateway runtime and separate deployment-plane architecture in `docs/overall-plan.md`, `docs/runtime/README.md`, and `docs/deployment/README.md` must remain unchanged in meaning.
- Historical plans and `plan/log.md` are factual records. Translation must not convert incomplete checks into passed checks or change hardware facts.
- Commands, filenames, protocol tokens, JSON keys, error codes, IP addresses, timings, speeds, angles, and validation levels must remain literal unless the surrounding prose alone is translated.

## Work Plan

1. Translate collaboration rules, repository entry documents, and plan workflow documentation.
2. Translate active architecture, network, runtime, deployment, development-session, and subsystem documentation.
3. Translate source README files and the Markdown protocol specification.
4. Translate all historical target plans and the factual work log without changing their recorded outcomes.
5. Scan all in-scope Markdown for remaining CJK characters, broken local links, secret material, malformed diffs, and unintended non-document changes.

## Risks and Boundaries

- This is a language-only documentation migration. It does not authorize source-code, protocol-schema, configuration, deployment, device connection, reset, or motion changes.
- Chinese text inside historical command output or externally defined literal protocol payloads may only remain if changing it would alter a byte-level fact; any such exception must be documented explicitly. The target is otherwise zero CJK characters in Git-managed Markdown.
- The existing user modification to `.vscode/settings.json` must not be staged or committed.

## Validation

- Enumerate all Git-managed Markdown files and require zero CJK matches.
- Verify every relative Markdown link target exists.
- Review architecture keywords and safety statements for semantic consistency.
- Scan intended files for credentials, private keys, local hotspot details, and temporary DHCP addresses.
- Run `git diff --check` and `git status --short --branch`.

## Actual Result

- Converted all 40 in-scope Markdown files to English, including collaboration rules, active architecture and subsystem documentation, source README files, plan templates, historical goal plans, and the factual work log.
- Manually rewrote the collaboration rules, repository entry point, active architecture/network/runtime/deployment baselines, source README files, and chassis safety document to preserve precise technical and safety terminology.
- Used a local offline model only for the first pass over historical records and secondary documents, then normalized project terminology and removed translation artifacts from critical documents. No repository content was sent to a translation service.
- Preserved commands, paths, protocol tokens, measurements, addresses, validation levels, hardware facts, and the distinction between completed and unperformed validation.
- No source code, schema, configuration, device filesystem, or hardware state changed. The user-owned `.vscode/settings.json` modification remained read-only and outside the commit.
- L0 validation passed: zero CJK or Unicode replacement characters remain in Git-managed Markdown, all relative Markdown link targets exist, fenced code blocks are balanced, and `git diff --check` passes.

## Unresolved Items

- Historical plans and log entries now use English but intentionally retain their original factual structure. They can receive future style-only copy editing if desired; no such editing may change recorded outcomes.
- Literal vendor or legacy filenames containing non-English characters are described in English rather than copied verbatim into Markdown. The raw-resource directories remain unchanged and read-only.

## Commit Intent

```text
docs: translate repository documentation to English
```
