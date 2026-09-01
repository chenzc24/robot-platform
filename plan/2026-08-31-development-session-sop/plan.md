# Record ESP32 unified session process with MaixCam

- Status:`completed`
- Responsible: Agent Records, user providing actual image acceptance results
- Highest validation level:`L0`

## Objective

Write validated ESP32 development links, MaixCam development/video links, day-to-day start-up and end sequences, detachments and solved/unsolved problems into actionable documents, and fill in the user's acceptance of WebRTC actual images.

## Initial state of the workspace

```text
## main...origin/main
 M .vscode/settings.json
```

`.vscode/settings.json` is that the user has failed to submit changes, not related to the target of this document; keep read-only, without saving, without submitting.

## Modifyable File

- `README.md`
- `docs/development-session.md`
- `docs/maixcam/video.md`
- `plan/2026-08-31-maixcam-rtsp-video/plan.md`
- `plan/2026-08-31-development-session-sop/plan.md`
- `plan/log.md`

## Read-only files and directories

- `.vscode/settings.json`
- All running codes, VS Code tasks, device configuration and local secrets
- `ESP32/`, `Camera/`, `Robot Arm_Claws/`
- ESP32, MaixCam and Mechanical Arm Device File System

## Shared Dependencies

- `docs/esp32/development.md`
- `docs/maixcam/development.md`
- `docs/maixcam/video.md`
- Completed ESP32 WebREPL and MaixCam SSH/RTSP L2

## Risk and safety door

- Risk: Recording processes and facts only, not changing software behaviour, device state, network or self-starting.
- Device: No connection or operating device required.
- User Operations: None.
- Backup and recovery: Git can restore document changes.
- Movement confirmed: not applicable.

## Expected work

1. Create a unified development session SOP, identify normal daily paths for two devices links.
2. Recording of the obstacles encountered in the first set-up, current treatment and remaining risks.
3. WebRTC's actual video is normal and the image needs to be rotated 90° by clock.
4. Link SOP from the project entry, update the fact log.

## Validation

- Check the Markdown structure, the factual consistency between links and records.
- Confirm not written to hotspots, SSH or WebREPL password and current DHCP address.
- `git diff --check`
- `git status --short --branch`

L0 is enough to cover this pure document target; do not execute device connection, video capture or motion validation.

## Actual results

- Add `docs/development-session.md`ESP32 development link, MaixCam code/video link, public network prefix, day-to-day start and end order, detachment, restoration of access and problem state.
- Item `README.md` The SOP has been linked, so that the process is not only in conversation.
- The original video document, the target plan and the fact log have been filled in:
- L0 Validation: Document Linked Target exists, no current DHCP address or private key is recorded,`git diff --check` By ... this target does not connect or modify any device ...

## Outstanding matters

- ESP32 WebREPL still needs to manually fill in its current address and password, without wireless atom deployment and health checks.
- MaixCam will still need manual exit after restart. `num`; rebooting cameras in the same opening speech may require physical rebooting.
- Video clockwise rotation 90° recorded but not implemented.

## Experience signal (for manual review)

The first set-up, the day-to-day start-up and failure recovery, will significantly increase the fragmentation branch; it may be worth following up on the development of a cross-device session, but this target does not automatically create an experience document.

## Intent to submit

```text
docs: record device development session workflow
```
