# MaixCam video communication

## 1. Current boundary

At this stage, only MaixCam's video link to the computer is set up, without a unified console, visual recognition, ESP32 communication or robot arm control.

```text
MaixCam GC4653
  └ - NV21 Collect / H.264
      └─ RTSP :8554/live
          Ideas-PyAV direct detection and capture frames
          └-FFmpeg-c:v copy (computer, unpacking/repackaging only)
              └ - MediaMTX (computer)
                  ├─ RTSP 127.0.0.1:8555/maixcam
                  ├─ HLS  http://127.0.0.1:8888/maixcam/index.m3u8
                  └─ WebRTC http://127.0.0.1:8889/maixcam/
```

MaixVision and MaixCode are not part of the chain. SSH/SCP is only responsible for code deployment, process start-up and log, and no continuous video.

## 2. Default media parameters

- Resolution: 1280 x 720.
- Encoding: H.264.
- Target frame rate: 20 fps.
- Target code rate: 2 Mbps.
- Device RTSP port: 8554.
- Path:`/live`.
- RTSP accepts priority use of TCP to avoid the Windows firewall blocking the RTP/UDP package.

MaixPy RTSP requires cameras to use NV21, which is `image.Format.FMT_YVU420SP`... that the video process calls as soon as MaixPy is imported `comm.rm_default_comm_listener()`, release the system default UART0 protocol listening device; video code does not read and write any robot business trails.

Local source code has been split into CLI, video service, MaixPy backend, camera resource ownership and structured state module, and additional PID attribution for Shell launch. The reconstruction is currently only using local false backend tests and MaixCam has not been uploaded; the results of this section 5 are from pre-restructuring versions already deployed.

## 3. Daily operations

Run the following tasks in VS Code:

1. MaixCam exits self-started on device screen after restarting `num` application;it does not occupy cameras with RTSP services.
2. `MaixCam Video: Start RTSP`: Upload and start device RTSP service.
3. `MaixCam Video: Probe direct`: Directly receive and save 10 seconds `tmp/maixcam-frame.png`.
4. `MaixCam Video: Start PC relay`: Activate computer-side FFmpeg compatibility bridge and MediaMTX forwarding service.
5. `MaixCam Video: Probe relay`: Transmit re-receiving and grab frames through this machine RTSP.
6. `MaixCam Video: Open WebRTC`: Open the WebRTC page with MediaMTX in the browser.
7. `MaixCam Video: Stop RTSP` and `Stop PC relay`: Stop the correspondence process.

Local remodeling has increased. `Status`, `Show recent log`, `PC relay status` and `Start development session` Mission. These missions have been checked through JSON's static system and have not yet been uploaded on the remodeled version.

Command line equivalent operation:

```powershell
ssh robot-maixcam /root/robot-platform/video/start.sh
.venv\Scripts\python.exe tools\maixcam\rtsp_probe.py --seconds 10
tools\maixcam\mediamtx.ps1 -Action start
.venv\Scripts\python.exe tools\maixcam\rtsp_probe.py --url rtsp://127.0.0.1:8555/maixcam --seconds 10
```

The probe will decipher the mDNS name as IPv4. The current hotspots simultaneously release an unattainable device IPv6 address, which may cause FFmpeg/PyAV to wait for a long time; do not submit the current DHCP IPv4 to the repository.

## 4. Computer side compatibility bridge and MediaMTX

The current computer uses MediaMTX v1.20.0 and FFmpeg 9.1 Windows amd64 in Git ignore directory:

```text
.tools/mediamtx-v1.20.0/
.tools/ffmpeg-9.0.1/
```

Both SHA256 published packages have matched the publisher's verification values. MaixCam's RTSP session declared H264 package mode 0, but actually contained a FU-A fraction; MediaMTX direct pull shows the path ready but cannot receive the media bytes. `-c:v copy` Unpack and repackage, and push it to MediaMTX as publisher. The process does not decode, recode, and does not change the resolution and target code.

Can submit Templates as `config/mediamtx.example.yml`;actual `config/mediamtx.local.yml` Ignored by Git. `maixcam-6c7d.local` Query for current IPv4, but do not write DHCP addresses to configuration or repository. MediaMTX `maixcam` The path only accepts the machine FFmpeg publicsher.

New computer installed from [MediaMTX Releases](https://github.com/bluenviron/mediamtx/releases) Download v1.20.0 Windows amd64, and from [Official download page of FFmpeg](https://ffmpeg.org/download.html) Select Windows amd64 to release the package. Verify that the publisher SHA256 depresses to the above directory and create a local configuration:

```powershell
Copy-Item config\mediamtx.example.yml config\mediamtx.local.yml
```

`tools/maixcam/mediamtx.ps1` Only the task is to parse the current device IPv4, sequentially suspend two mature tools, record PIDs and logs, and not achieve media protocols or decoding.

Configure only listening computer loop addresses, close unused RTMPs, SRTs and MoQ portals. When other computers are needed in the future, a separate network and validation target should be created, and the port should not be exposed directly to uncontrolled networks.

## Verified output

| Peer | Current round of validation |
|---|---|
| MaixCam RTSP `rtsp://maixcam-6c7d.local:8554/live` | PyAV decoded with actual grab frames. |
| RTSP `rtsp://127.0.0.1:8555/maixcam` | Reactivated 30 seconds to decode 592 frames, 1280 x 720, 20 fps |
| HLS `http://127.0.0.1:8888/maixcam/index.m3u8` | HTTP 200 and FFmpeg decoded through |
| WebRTC `http://127.0.0.1:8889/maixcam/` | Playpage HTTP 200, user confirmed actual stream is normal |

User acceptance confirms that the image requires a clockwise rotation of 90°. This requirement is documented, but this video communication target does not modify the original coding stream; The rotation will be carried out uniformly in the subsequent display and visual coordinates system target.

## 6. Cessation and recovery

- This target does not set the device to start automatically; maixCam does not run the video service by default after restart.
- Device confirm/return key may terminate the current MaixPy video process.
- Use `stop.sh` After normal release of the camera, there is a risk that the current multimedia drive will fail again in the same system session; if logs appear `No buffer space available` Or the initialization of the ISP should stop the residual process and physically restart the device.
- Try to force the termination of the process first `stop.sh`;do not run two cameras at once.
- `Stop PC relay` Stop the FFmpeg, then MediaMTX;

## Not yet included

- The confirmed clockwise displays a 90-degree rotation, as well as malformations, exposure and colouring.
- The detection box, the target coordinates and the identification results are superimposed.
- Browser console layout and device control.
- Autostart, guard, health check and cut-off recovery strategy.
- Video, recycling storage and data retention policy.

These content sets up follow-up targets; Video cannot be the only feedback on robotic safety.
