# MaixCam源码

本目录是MaixCam正式源码的本地可信源。设备文件系统只作为部署目标，设备上的有效修改必须回收到本目录。

## 当前状态

- 已建立基于OpenSSH的无线诊断、SCP部署和终端通道。
- `app/probe.py` 是无运动开发通道探针，不导入 `maix`，不初始化摄像头、UART、GPIO或机械臂链路。
- `video/rtsp_server.py` 是H.264 RTSP命令行入口，`video_service.py` 封装可注入后端、摄像头所有权、启停回滚和结构化状态；它们不包含识别、ESP32或机械臂控制逻辑。
- 真实视觉识别服务、ESP32串口和机械臂网关尚未迁移。

开发与恢复流程见 [`../../docs/maixcam/development.md`](../../docs/maixcam/development.md)，视频链路见 [`../../docs/maixcam/video.md`](../../docs/maixcam/video.md)。

运行时契约和本地重构边界见 [`../../docs/runtime-foundation.md`](../../docs/runtime-foundation.md)。
