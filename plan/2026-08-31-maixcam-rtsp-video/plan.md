# MaixCam to PC RTSP video communication

- Status:`completed`
- Responsible: Agent execution, user responsible for power supply, camera environment and necessary screen operations
- Highest validation level:`L2`

## Objective

Without access to ESP32, robot arm or unified console, establish MaixCam Pro for continuous video communication to develop a computer: The device runs a version-managed RTSP/H.264 service, the computer uses standard tools to detect, receive, detect and capture actual video frames. After the adoption of the RTSP, evaluate and validate MediaMTX as the standard computer side repeater layer; This target does not develop the final console interface.

MaixVision is no longer a project development, deployment or video debugging dependent. VS Code and SSH/SCP are responsible for source deployment and logs, RTSP is responsible for video.

## Initial state of the workspace

```text
## main...origin/main
 M .vscode/settings.json
```

`.vscode/settings.json` is the user's existing MicroPython button modification, not related to this target; keep read-only, do not overwrite, do not save, do not submit. The rest of the workspace is clean.

## Modifyable scope

- `plan/2026-08-31-maixcam-rtsp-video/plan.md`
- `plan/log.md`
- `docs/overall-plan.md`
- `docs/network/README.md`
- `docs/maixcam/`
- `src/maixcam/`
- `tests/maixcam/`
- `tools/maixcam/`
- `config/` Unhidden Video Configuration Template
- `.vscode/tasks.json`
- Git ignored it. `.tools/`, `tmp/` And grab frame output
- MaixCam `/root/robot-platform/video/` A stand-alone deployment directory and processes/log files in this directory

## Read-only

- User not submitted `.vscode/settings.json`
- `Camera/`, `ESP32/`, `Robot Arm_Claws/` Source
- ESP32, Mechanical Arm, TCP 232 and their configuration
- MaixCam `/maixapp/`, `/boot/`,system application, self-start and system solid
- existing device backup;do not overwrite or submit

## Sharing dependency and decision-making

- Use MaixPy official `maix.rtsp`, NV21 camera format and H.264 RTSP, do not develop decoding or media protocols.
- Develop deployment plane SSH/SCP, video plane RTSP; SSH does not undertake continuous video transmission.
- The first validation entrance is MaixCam's original RTSP; MediaMTX is only accessible after the primary link, avoiding both layers of failure.
- This target allows camera capture. MaixPy may briefly create the default UART0 telecommunications monitor when importing; The video process must immediately call the official release interface, not read and write business links, nor initiate the ESP32 link, robot arm UART, TCP232, GPIIO or motion module.
- Video is only for observation, not as the only security feedback.

## Implementation steps

1. Read-only confirmation device online, current camera occupancy and RTSP port status; confirm recovery path available.
2. Check that the computer already has FFmpeg/ffplay and available media tools; only from official sources to Git ignore directories when missing.
3. Develop a minimum RTSP service, configure models and local static tests, without setting the device to start on.
4. Deployment through SCP `/root/robot-platform/video/`, run and maintain logs in the previous or stopable backstage mode.
5. Validate TCP 8554, RTSP flow information from the computer, receiving and extracting continuously from the actual frame; record resolution, code, frame and basic stability.
6. When the original RTSP is stabilized, install and configure MediaMTX as necessary to verify its extraction and re-issuance links; if there is no browser consumer at the current stage, it is clearly recorded as a follow-up item rather than a disguise.
7. Update overall, network and MaixCam files, remove MaixVision's day-to-day dependency, add VS Code video tasks and restore methods.

## User needs assistance

- Keep MaixCam connected to power and hot spots, and keep regular, non-sensitive test images on camera.
- If the device screen already has an occupied camera application, the user returns the main interface by hint or stops the application.
- The final frame results confirm the direction of the picture, clarity and acceptable delay.
- This target does not need to be connected to ESP 32, a robot arm or an exercise safety door.

## Validation

- L0: Python/JSON/YAML Syntax, Document Link, Secret Scan,`git diff --check`.
- L1: Configure the resolution, command generation or no hardware-aided logical testing; ESP32 and MaixCam regression tests.
- L2: SSH deployment, RTSP port, computer media detection, continuous reception, actual frame grab and stop/restart recovery.
- Do not execute robot arm or chassis motion, do not change self-start, network, UART and system solid.

## Restore Path

- Stop. `/root/robot-platform/video/` The process initiated by the Central Goal.
- Deleting this stand-alone directory would eliminate the deployment of the device; `/maixapp/` And the system is self-starting.
- When RTSP occupancy or camera initialization fails, view the log through SSH, stop the process and return the device main interface.
- When Wi-Fi failed to restore SSH by device screen or USB virtual network adapter; complete backup remains unchanged.

## Actual results

- Already `/root/robot-platform/video/` Deployment of independent MaixPy RTSP/H.264 service, unmodified `/maixapp/`, self-starting or system solid, without connection to ESP 32, TCP 232 and robot arm business chain Lou.
- Original RTSP directly authenticates H.264, 1280 x 720, 20 fps, decoding 286 frames in 15 seconds and preserving the real picture.
- MaixCam RTSP was found to be declaring Packetization Mode 0 but using FU-A fractions without media bytes for MediaMTX; read FFmpeg 9.1 `-c:v copy` Resealed and pushed to MediaMTX v1.20.0, uncoded and recoded.
- This machine RTSP continues to decode 592 frames for 30 seconds after stop/restart, measured 20.0 fps; MediaMTX API confirms that the path is ready and has a real reception bytes.
- HLS returned HTTP 200 and decoded via FFmpeg; WebRTC played page returned HTTP 200.
- The user then confirmed the actual video stream on the WebRTC page and confirmed that the image should rotate 90°.
- Joined VS Code upload, launch, direct line detection, relay detection and WebRTC mission opening, MaixVision and MaixCode are no longer dependent on the project.

## Outstanding matters

- Start since device restart `num` Application will take over the camera, and this target has no permission to change self-start;
- Current multimedia drive is possible once released in the same opening speech `No buffer space available`; needing physical reboot, no system drive modified in this round.
- The actual video stream of WebRTC has been confirmed by the user; the timewise rotation of the image 90° and the corresponding coordinate system has not been implemented.

## Intent to submit

```text
feat: establish MaixCam RTSP video link
```
