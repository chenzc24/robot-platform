# MaixCam headless video deployment - 2026-09-10

## Scope and result

Only the MaixCam video service and its local PC relay were updated. No ESP32,
robot-arm gateway, UART business command, chassis command or arm command was
started or changed.

The target identity was `maixcam-6c7d`, `riscv64`. The overwritten device files
were copied to the ignored local backup
`device-backups/maixcam/20260910-pre-video-8b8f83f` before activation.

## Published files

The following SHA-256 values were verified after activation:

| Device file | SHA-256 |
|---|---|
| `video/video_service.py` | `a4eac46163d6b56b4ff0239348dd35208676e07defa8174d10a8bdb026e28ce2` |
| `video/start.sh` | `a1d837555bfcaf843a720897fc08e4d5884cc7c8977912fa56caba8650a1fe62` |
| `video/stop.sh` | `e59715231e80a22f809bf4fd357085c38971991f24821f765b934ef12c556ca9` |
| `video/status.sh` | `15a13d24186281d50f004f1446de6414a7e0138b84eab26bb02045c0b6487d4f` |
| `video/run_video_service.sh` | `b57ac3acbcc7b2ef928544564d8e252e1a7bc6fa2fa914832e060fefa523da81` |

The staged Python file compiled on-device and all four shell files passed
`sh -n` before activation.

## Launcher handoff and L2 evidence

The video owner wrapper stopped the verified launcher supervisor and sent TERM
to the verified launcher. Because its parent was stopped, the released launcher
remained temporarily visible as zombie PID 1986; the wrapper correctly treated
state `Z` as resource release. No force signal was needed in the successful
start. The service reported both the default key-exit listener and default UART
listener removed before publishing RTSP.

Observed result:

- device RTSP: running, H.264, 1280 x 720, nominal 20 fps;
- PC FFmpeg/MediaMTX relay: ready;
- loopback RTSP probe: 96 frames in 6.031 seconds, measured 20.0 fps;
- first decoded frame: 2.781 seconds;
- captured verification frame: ignored `tmp/maixcam-deploy-verify.png`.

This is an observation-only L2 video result. It does not establish AprilTag
metrology, robot-arm readiness, chassis readiness or coordinated motion.
