# MaixCam源码

本目录是MaixCam正式源码的本地可信源。设备文件系统只作为部署目标，设备上的有效修改必须回收到本目录。

## 当前状态

- 已建立基于OpenSSH的无线诊断、SCP部署和终端通道。
- `app/probe.py` 是无运动开发通道探针，不导入 `maix`，不初始化摄像头、UART、GPIO或机械臂链路。
- 真实视觉服务、ESP32串口和机械臂网关尚未迁移。

开发与恢复流程见 [`../../docs/maixcam/development.md`](../../docs/maixcam/development.md)。
