# MaixCam到电脑RTSP视频通信

- 状态：`completed`
- 负责人：Agent执行，用户负责设备供电、镜头环境与必要的屏幕操作
- 最高验证等级：`L2`

## 目标

在不接入ESP32、机械臂或统一控制台的前提下，建立MaixCam Pro到开发电脑的持续视频通信：设备运行受版本管理的RTSP/H.264服务，电脑使用标准工具发现、接收、探测和抓取实际视频帧。直接RTSP通过后，再评估并验证MediaMTX作为电脑侧标准转发层；本目标不开发最终控制台界面。

MaixVision不再作为项目开发、部署或视频调试依赖。VS Code与SSH/SCP负责源码部署和日志，RTSP负责视频。

## 工作区初始状态

```text
## main...origin/main
 M .vscode/settings.json
```

`.vscode/settings.json` 是用户已有的MicroPython按钮修改，与本目标无关；保持只读，不覆盖、不暂存、不提交。其余工作区干净。

## 可修改范围

- `plan/2026-08-31-maixcam-rtsp-video/plan.md`
- `plan/log.md`
- `docs/overall-plan.md`
- `docs/network/README.md`
- `docs/maixcam/`
- `src/maixcam/`
- `tests/maixcam/`
- `tools/maixcam/`
- `config/` 中无秘密的视频配置模板
- `.vscode/tasks.json`
- Git忽略的 `.tools/`、`tmp/` 和抓帧输出
- MaixCam `/root/robot-platform/video/` 独立部署目录及该目录内的进程/日志文件

## 只读范围

- 用户未提交的 `.vscode/settings.json`
- `Camera/`、`ESP32/`、`Robot Arm_Claws/` 原始资料
- ESP32、机械臂、TCP232及其配置
- MaixCam `/maixapp/`、`/boot/`、系统应用、自启动和系统固件
- 既有设备备份；不得覆盖或提交

## 共享依赖与决策

- 采用MaixPy官方 `maix.rtsp`、NV21摄像头格式和H.264 RTSP，不自研编解码或媒体协议。
- 开发部署平面为SSH/SCP，视频平面为RTSP；SSH不承担持续视频传输。
- 第一验证入口为MaixCam原生RTSP；MediaMTX只在原生链路通过后接入，避免同时排查两层故障。
- 本目标允许开启相机采集。MaixPy导入时可能短暂创建默认UART0通信监听器；视频进程必须立即调用官方释放接口，不读写业务串口，也不初始化ESP32链路、机械臂UART、TCP232、GPIO或运动模块。
- 视频只用于观察，不作为唯一安全反馈。

## 实施步骤

1. 只读确认设备在线、当前摄像头占用和RTSP端口状态；确认恢复路径仍可用。
2. 检查电脑已有FFmpeg/ffplay及可用媒体工具；缺失时仅从官方来源安装到Git忽略目录。
3. 编写最小RTSP服务、配置模型和本地静态测试，不设置设备自启动。
4. 通过SCP部署到 `/root/robot-platform/video/`，以前台或可停止的后台方式运行并保留日志。
5. 从电脑验证TCP 8554、RTSP流信息、持续接收和实际帧抓取；记录分辨率、编码、帧率与基本稳定性。
6. 原生RTSP稳定后，按需要安装并配置MediaMTX，验证其拉取和重新发布链路；若当前阶段无浏览器消费者，则明确记录为后续项而非伪装完成。
7. 更新总体、网络和MaixCam文档，移除MaixVision日常依赖，增加VS Code视频任务和恢复方法。

## 用户需要协助

- 保持MaixCam供电和热点连接，镜头前保持普通、无敏感信息的测试画面。
- 若设备屏幕已有占用摄像头的应用，由用户按提示退回主界面或停止该应用。
- 根据最终抓帧结果确认画面方向、清晰度和可接受延迟。
- 本目标不需要连接ESP32、机械臂或执行运动安全门。

## 验证

- L0：Python/JSON/YAML语法、文档链接、秘密扫描、`git diff --check`。
- L1：配置解析、命令生成或无硬件辅助逻辑测试；既有ESP32与MaixCam回归测试。
- L2：SSH部署、RTSP端口、电脑媒体探测、持续接收、实际抓帧及停止/重启恢复。
- 不执行机械臂或底盘运动，不更改自启动、网络、UART和系统固件。

## 恢复路径

- 先停止 `/root/robot-platform/video/` 中本目标启动的进程。
- 删除该独立目录即可撤销设备部署；不影响 `/maixapp/` 和系统自启动应用。
- RTSP占用或相机初始化失败时，通过SSH查看日志、停止进程并返回设备主界面。
- Wi-Fi失败时通过设备屏幕或USB虚拟网卡恢复SSH；既有完整备份保持不变。

## 实际结果

- 已在 `/root/robot-platform/video/` 部署独立MaixPy RTSP/H.264服务，未修改 `/maixapp/`、自启动或系统固件，也未连接ESP32、TCP232和机械臂业务链路。
- 原生RTSP直连验证H.264、1280×720、20 fps，15秒内解码286帧并保存真实画面。
- 发现MaixCam RTSP声明packetization mode 0但使用FU-A分片，MediaMTX直拉路径就绪却无媒体字节；改为FFmpeg 9.0.1 `-c:v copy` 重封装后推给MediaMTX v1.20.0，无解码和重新编码。
- 本机RTSP中继在停止/重启后连续30秒解码592帧，实测20.0 fps；MediaMTX API确认路径就绪且有真实接收字节。
- HLS清单返回HTTP 200并通过FFmpeg解码；WebRTC播放页返回HTTP 200。
- 用户随后已在WebRTC播放页确认实际视频流正常，并确认画面应顺时针旋转90°。
- 已加入VS Code上传、启停、直连探测、中继探测和WebRTC打开任务，MaixVision和MaixCode不再属于项目依赖。

## 未解决事项

- 设备重启后自启动 `num` 应用会占用摄像头，本目标没有权限改动自启动；启动RTSP前需现场退出该应用。
- 当前多媒体驱动在同一开机会话内释放后再次初始化可能报 `No buffer space available`；需物理重启恢复，本轮没有修改系统驱动。
- WebRTC实际视频流已经用户确认正常；画面顺时针旋转90°及相应坐标系处理尚未实施。

## 提交意图

```text
feat: establish MaixCam RTSP video link
```
