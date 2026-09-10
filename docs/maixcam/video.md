# MaixCam Video Receive Chain

## 1. Runtime boundary

The video path is independent of the robot-arm and chassis command paths:

```text
MaixCam GC4653
  -> NV21 capture and H.264 encoding
  -> RTSP rtsp://maixcam-6c7d.local:8554/live
  -> FFmpeg stream copy on the computer
  -> MediaMTX loopback relay
       |- RTSP   rtsp://127.0.0.1:8555/maixcam
       |- HLS    http://127.0.0.1:8888/maixcam/index.m3u8
       `- WebRTC http://127.0.0.1:8889/maixcam/
  -> localhost console MediaMTX WebRTC viewport
  -> parallel RTSP input reserved for future Python vision inference
```

MaixVision and MaixCode are not part of this path. SSH/SCP manages files and processes; it does not transport video. Starting or stopping this chain must not connect the robot-arm gateway, UART0/TCP232 business protocol, ESP32, CAN, or any motion endpoint.

## 2. Media baseline

- Source resolution: 1280 x 720.
- Encoding: H.264 Main profile.
- Target frame rate: 20 fps.
- Target bitrate: 2 Mbps.
- Device endpoint: TCP RTSP port 8554, path `/live`.
- Console endpoint: loopback TCP RTSP port 8555, path `/maixcam`.
- Display orientation: clockwise 90 degrees. The encoded stream remains unmodified; the console owns display and AprilTag overlay-coordinate rotation.

MaixPy RTSP capture requires `image.Format.FMT_YVU420SP`. Importing MaixPy
initializes two unrelated listeners: the default communication listener may own
UART0, and the default key listener turns the physical OK key into application
exit. The headless video service removes both before starting the camera. The
video service does not read, write, or forward robot-arm commands.

`video/start.sh` launches `run_video_service.sh`, which coordinates the real
launcher processes before importing MaixPy. It pauses the verified launcher
supervisor, gives a verified launcher process one second to exit normally, then
checks its executable path again before force-releasing it when necessary. The
wrapper restores the supervisor when video exits. If the arm runtime already
holds the supervisor in the stopped state, the video wrapper preserves that
ownership and does not resume it. Unknown or identity-changing processes are
never signalled. This process-level handoff is required because the Python
`ResourceRegistry` only coordinates owners inside one process.

Because the stopped supervisor is the launcher's parent, a normally terminated
launcher can remain visible briefly as a zombie. The wrapper treats state `Z`
as released rather than waiting for `kill -0` to become false; a zombie owns no
camera or UART resource and is reaped after the supervisor is resumed.

## 3. Computer prerequisites

Create the project environment and install the locked dependencies:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

The localhost preview uses the browser MediaMTX WebRTC page and adds no Python
decoder dependency. PyAV and NumPy remain installed for the legacy Qt fallback,
receive probes, and future Python inference.

The ignored local tools are:

```text
.tools/mediamtx-v1.20.0/
.tools/ffmpeg-9.0.1/
```

Copy `config/mediamtx.example.yml` to ignored `config/mediamtx.local.yml`. Configure the console's ignored `config/console.local.json` with:

```json
{
  "video": {
    "rtsp_url": "rtsp://127.0.0.1:8555/maixcam",
    "webrtc_url": "http://127.0.0.1:8889/maixcam/",
    "connect_timeout_seconds": 3.0,
    "snapshot_directory": "snapshots"
  }
}
```

Do not commit a temporary DHCP address. The device source is resolved from `maixcam-6c7d.local` to IPv4 when the relay starts.

## 4. Normal operating flow

From the repository root:

```powershell
# Start or confirm the MaixCam source. This is idempotent for an owned video PID.
ssh robot-maixcam /root/robot-platform/video/start.sh

# Start the computer relay. Success now means that /maixcam is actually ready.
.\tools\maixcam\mediamtx.ps1 -Action start

# Optional deterministic receive check.
.\.venv\Scripts\python.exe tools\maixcam\rtsp_probe.py `
  --url rtsp://127.0.0.1:8555/maixcam `
  --seconds 6
```

Then launch `.\robot-console.cmd`. The camera viewport loads the configured
WebRTC page directly; no device command connection is opened as a side effect.

To stop only the computer side:

```powershell
.\tools\maixcam\mediamtx.ps1 -Action stop
```

To release the MaixCam camera as well:

```powershell
ssh robot-maixcam /root/robot-platform/video/stop.sh
```

Stop the console preview before stopping the relay. The relay stop order is FFmpeg first, then MediaMTX.

## 5. Why the FFmpeg bridge exists

The MaixCam stream declares H.264 packetization mode 0 but has emitted FU-A fragments. A direct MediaMTX pull can therefore report a ready path without receiving usable media. FFmpeg performs `-c:v copy` depacketization and repacketization, then publishes to MediaMTX. It does not decode, transcode, rotate, resize, or change the target bitrate.

`tools/maixcam/mediamtx.ps1` owns only its recorded FFmpeg and MediaMTX PIDs. Its start command now waits for the MediaMTX API to report path `maixcam` as both `ready` and `online`; a live process pair without a published path is reported as `VIDEO_RELAY_NOT_READY`, not as success.

The legacy PySide6 console decoder:

- uses RTSP over TCP;
- applies separate PyAV open and read timeouts;
- copies RGB pixels into a Qt-owned image before crossing threads;
- closes the PyAV container in the decoder thread that owns it;
- supports repeated start, frame decode, snapshot, and stop cycles; and
- reports a stop timeout as degraded instead of force-closing PyAV from another thread.

## 6. Verified L2 evidence

Live validation on 2026-09-02 produced:

| Check | Result |
|---|---|
| MaixCam direct RTSP | H.264, 1280 x 720, nominal 20 fps; 154 frames decoded in 8.016 s; first frame in 1.797 s |
| Computer relay startup | Returned success after 5.496 s, only after the MediaMTX path became ready |
| Relay RTSP | H.264, 1280 x 720, measured 20.008 fps; 105 frames decoded in 6.011 s; first frame in 2.207 s |
| HLS and WebRTC pages | HTTP 200 |
| Console decoder | Two consecutive start/frame/snapshot/stop cycles passed; both stops returned true |
| Orientation | Captured raw frame was sideways; the console default clockwise 90-degree display rotation is required |

No chassis, CAN, robot-arm, UART, or TCP232 command was sent during this validation.

## 7. Failure handling

| Symptom | Check and response |
|---|---|
| Device port 8554 is closed | Check SSH and the device video log, then run the owned `start.sh`. Do not kill an unknown camera process. |
| `VIDEO_START_REFUSED launcher_identity_changed` | Inspect the process table. The wrapper refuses to signal a PID whose executable identity changed. |
| Relay says `NOT_RUNNING` | Confirm the source RTSP first, then start the relay. |
| Relay says `NOT_READY` | Inspect `logs/mediamtx/ffmpeg-stderr.log` and MediaMTX logs; stop the owned pair before retrying. |
| Immediate RTSP 404 after startup | The current script waits for path readiness. Treat a recurrence as a relay-start defect and retain the logs. |
| Console remains offline while the relay probe works | Verify the local RTSP URL and that PyAV plus NumPy are installed in the same interpreter that launches the UI. |
| Preview stop reports degraded | Allow the configured read timeout to release the decoder; do not force-close the PyAV container from another thread. |
| ISP or buffer allocation fails | Stop the owned video process. If the multimedia driver does not recover, physically restart MaixCam before starting one camera owner. |

## 8. Remaining work

- The modular video service and `status.sh` were deployed on 2026-09-03. Live
  readiness, direct decoding, and stop/start passed after fixing buffered
  readiness output and post-MaixPy signal registration. See the
  [deployment evidence](../deployment/2026-09-03-esp32-maixcam.md).
- The PC AprilTag v1 worker now consumes the local RTSP route and publishes a
  calibrated observation overlay. Live oblique-angle/metrology acceptance,
  exact WebRTC frame correlation, exposure controls, and recording/retention
  policy remain outstanding.
- Decide whether the video service should start automatically after MaixCam boots.

Video is observability data and never the only safety feedback for robot motion.
