# MaixCam Console Video Chain

- Status: `completed`
- Responsible: `joint`
- Highest validation level: `L2`

## Objective

Verify and tune the non-motion video path from MaixCam RTSP through the computer-side FFmpeg/MediaMTX relay into the unified console, while leaving the robot-arm runtime and all motion-capable paths untouched.

## Initial state of the workspace

`git status --short --branch` at the active console worktree:

```text
## target/control-console-manual-l3...origin/target/control-console-manual-l3
```

The worktree is clean. The repository's primary worktree has an unrelated user-owned `.vscode/settings.json` change; it will not be modified, staged, or committed by this goal.

## Modifyable File

- `plan/2026-09-02-maixcam-console-video-chain/plan.md`
- `plan/log.md`
- `docs/maixcam/video.md` and console video documentation, if factual corrections are required
- `src/console/ui/` and directly related tests, only if the live L2 check exposes a video receive defect
- ignored local video configuration, relay state, logs, and probe captures
- MaixCam video service under `/root/robot-platform/video/`, limited to status/start/stop and logs

## Read-only files and directories

- `ESP32/`, `Camera/`, and `Robot Arm_Claws/`
- `src/maixcam/arm_gateway/`, robot-arm deployment files, UART0/TCP232 configuration, and robot-arm LAN1/LAN2
- ESP32 runtime and device filesystem
- secret-bearing SSH configuration, credentials, and local environment files

## Shared Dependencies

- Runtime boundary in `docs/overall-plan.md`: MaixCam owns video and the arm gateway, while the computer talks directly to ESP32 for chassis control.
- Video baseline in `docs/maixcam/video.md`.
- MaixCam source RTSP endpoint `rtsp://maixcam-6c7d.local:8554/live`.
- Computer relay endpoints, especially `rtsp://127.0.0.1:8555/maixcam` for the console.
- The console's existing PyAV decoder and clockwise 90-degree display requirement.

## Risk and safety door

- Risk: L2 network/process/resource-ownership diagnostics. Starting a second MaixPy camera owner could conflict with the existing video or a colleague's process, so current ownership must be checked before any start/stop action.
- Hardware: MaixCam and development computer only.
- User operations: keep MaixCam and the computer on the current hotspot; report if the device screen or camera application needs manual intervention.
- Backup and recovery: no firmware, boot configuration, or device source overwrite is planned. Stop only processes proven to belong to the video service; physical MaixCam restart remains the recovery path for ISP/buffer exhaustion.
- Motion gate: not applicable. No chassis, arm, UART, TCP232, CAN, or motion command may be sent.

## Expected work

1. Inspect MaixCam reachability, the video service, local relay ownership, console video configuration, and recent video logs without touching the arm route.
2. Establish the direct RTSP stream, then the local relay, and collect deterministic decode/frame-rate evidence.
3. Connect the existing console decoder, verify stable start/stop/reconnect and the required clockwise 90-degree presentation, and fix only demonstrated receive-chain defects.
4. Record actual L2 results and residual risks, then commit and push only declared files.

## Validation

- Direct RTSP probe: decoded frame count, resolution, codec, measured frame rate, first-frame latency, and captured frame.
- Relay RTSP probe with the same evidence.
- Console video log/status: successful decoder start, decoded frames, stable stop/reconnect, and no arm or chassis commands.
- Relevant local tests if source changes.
- `git diff --check`
- `git status --short --branch`

L2 covers a real MaixCam and computer network path but explicitly excludes motion and robot-arm resource access. A camera-owner conflict or unknown process is a stop condition rather than authorization to kill it.

## Actual results

- The MaixCam resolved to its current hotspot IPv4, SSH was reachable, and no video or robot-arm Python process was running before the test. The previously deployed compact video service was started without deploying or modifying device files.
- Direct RTSP decoded H.264 at 1280 x 720 with a nominal 20 fps: 154 frames in 8.016 seconds and first frame in 1.797 seconds.
- The first relay attempt reproduced a startup race: the process wrapper returned before FFmpeg had published `/maixcam`, so an immediate client received RTSP 404. The wrapper now waits for MediaMTX to report path `maixcam` as ready and online, and status distinguishes `NOT_READY` from `RUNNING`.
- The corrected relay returned after 5.496 seconds. An immediate relay probe decoded 105 frames in 6.011 seconds at 20.008 measured fps, with first frame in 2.207 seconds. HLS and WebRTC pages returned HTTP 200.
- The console environment initially split PySide6 and PyAV across two interpreters, and the locked dependencies omitted NumPy. A project-local environment was built and NumPy was added because the Qt frame adapter requires `frame.to_ndarray()`.
- A live decoder cycle then exposed unsafe cross-thread PyAV shutdown: the first frame and snapshot succeeded, but stop timed out and a second start ended in an access violation. The decoder now uses PyAV open/read timeouts and closes the container only in its owner thread.
- Two subsequent live decoder start/frame/snapshot/stop cycles passed. Full offscreen UI integration also passed: hardware-mode connect, online state, a real 1280 x 720 frame bound to the canvas, 90-degree display state, snapshot, disconnect, and final offline state.
- Six isolated test suites passed 207 tests total: console 44, development 23, ESP32 57, MaixCam 46, protocol 28, and robot arm 9. UI smoke, PowerShell parsing, and `git diff --check` also passed.
- No chassis, CAN, ESP32, robot-arm, UART, TCP232, or motion command was sent. The MaixCam video source and computer relay remain running for operator viewing.

## Outstanding matters

- The live MaixCam still contains the previously validated compact video service. Deployment of the repository's newer modular service and `status.sh` was intentionally deferred because this goal did not need a device rewrite and the robot arm was in use by another colleague.
- The visible UI is running with the corrected interpreter and configuration. Automated full-UI integration passed; the operator may select Hardware and Connect preview for visual acceptance without connecting either control endpoint.
- Autostart, vision inference, calibrated overlays, exposure controls, and recording policy remain separate goals.

## Experience signal (for manual review)

- Process liveness is insufficient readiness evidence for a media relay; the published path must be queried.
- A PyAV container must not be force-closed from a different thread than the decoder thread that owns it.

## Intent to submit

```text
fix(video): stabilize MaixCam console receive chain
```
