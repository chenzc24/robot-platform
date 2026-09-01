# 建立扁平连接管理与维护CLI

- 状态：`completed`
- 负责人：Agent实施，用户现场提供已接入手机热点的设备
- 最高验证等级：`L2`

## 目标

在不增加后台守护进程、不混入部署与运动控制的前提下，提供一个扁平的 `robot` CLI：一层负责ESP32、MaixCam和电脑视频中继的发现、幂等连接与进程归属保护，一层负责三级状态、稳定错误码和下一步建议；同时提供受保护的状态、日志、停止、重启、强制终止和设备重启入口，供后续开发复用。

## 工作区初始状态

```text
## main...origin/main
 M .vscode/settings.json
```

`.vscode/settings.json` 是用户已有的MicroPython按钮修改，本目标保持只读，不覆盖、不暂存、不提交。当前分支与远端同步，其余路径干净。

## 可修改文件

- `robot.cmd`
- `tools/robot_cli.py`
- `tools/dev/connection_manager.py`
- `tests/dev/`
- `.vscode/tasks.json`
- `README.md`
- `docs/development-session.md`
- `docs/runtime-foundation.md`
- `plan/2026-09-01-flat-connection-cli/plan.md`
- `plan/log.md`

## 只读文件和目录

- `.vscode/settings.json`
- `src/esp32/legacy/`
- `ESP32/`、`Camera/`、`Robot Arm_Claws/`
- 本地秘密、SSH配置、设备配置、缓存和备份
- ESP32与MaixCam设备文件系统和启动配置
- TCP232、机械臂、CAN、电机和底盘控制路径

## 共享依赖

- `protocol/runtime-status.schema.json` 的结构化反馈原则；CLI默认只显示简化三级状态。
- `tools/maixcam/mediamtx.ps1` 的本机PID与可执行文件归属保护。
- MaixCam项目RTSP进程路径 `/root/robot-platform/video/rtsp_server.py` 和PID文件。
- ESP32 WebREPL端口8266只用于可达性检查，本目标不登录REPL、不上传、不复位。

## 风险和安全门

- 风险：错误的进程目标可能中断无关程序；设备重启可能改变运行状态；ESP32当前旧程序复位可能初始化CAN和电机。
- 设备：ESP32与MaixCam，执行L2发现、端口、SSH、RTSP和状态读取；允许在确认项目RTSP未运行时调用现有启动脚本，并幂等确保电脑侧媒体中继。
- 用户操作：保持设备接入同一手机热点；本轮不要求操作BOOT/RST或产生运动。
- 备份和恢复：不修改设备文件或启动配置；MaixCam仅启动缺失的视频进程，本机媒体中继可用现有脚本停止并重新启动。
- 运动确认：不适用。CLI中的ESP32重启必须保持保护拒绝；本轮不执行MaixCam停止、强杀或整机重启命令。

## 预期工作

1. 实现一次性、无后台进程的连接管理器，支持ESP32有界发现、MaixCam IPv4/SSH/RTSP检查、本机中继状态和单实例锁。
2. 实现 `connect/status/details/disconnect/ps/logs/stop/restart/kill/reboot` 命令、三级摘要、JSON输出、稳定退出码和目标归属保护。
3. 用假网络、假进程和假命令执行器覆盖幂等、模糊发现、部分运行、所有权不匹配、保护拒绝与命令路由。
4. 将四个日常入口加入VS Code，保留现有细粒度任务作为高级诊断。
5. 在当前热点下先执行只读L2状态检查；确认远端项目进程和启动脚本后执行幂等 `connect`，只启动缺失的MaixCam视频服务和电脑中继。

## 验证

- 新增CLI和连接管理器单元测试。
- 全部既有协议、ESP32和MaixCam本地测试。
- Python无缓存编译、VS Code JSON、正式源码语言、CLI帮助和JSON输出检查。
- L2：ESP32 TCP 8266、MaixCam SSH、RTSP端口和现有进程状态；启动缺失的MaixCam视频服务与电脑中继后复核状态。
- `git diff --check`
- `git status --short --branch`

L1覆盖命令路由、进程归属、状态汇总和失败反馈；L2只验证真实连接和缺失服务启动，不执行远端停止、强杀、整机重启、上传、复位或任何运动。

## 实际结果

- 新增根目录 `robot.cmd` 和两个英文Python模块，形成无后台守护进程的扁平CLI；日常命令为 `connect/status/details/disconnect`，维护命令为 `ps/logs/stop/restart/kill/reboot`。
- 统一只展示 `maixcam/esp32/camera/video` 四个检查和 `READY/DEGRADED/OFFLINE`三级总状态；所有命令支持JSON，退出码区分成功、异常、用法错误和保护拒绝。
- ESP32发现按显式值、成功缓存、ARP活跃候选和低并发同网段扫描依次执行；真实热点首轮并发扫描漏检8266后，该策略修正并再次确认ESP32在线。
- `connect`只启动缺失的设备RTSP和电脑中继，健康状态不重复启动；首次真实运行将MaixCam RTSP与本机FFmpeg/MediaMTX恢复，之后幂等运行3.29秒返回READY且 `changed=false`。
- Windows外部进程输出改用临时文件而非捕获管道，修复FFmpeg/MediaMTX启动后CLI不退出；真实 `restart relay` 在6.76秒内完成，后续统一状态仍为READY。
- 进程维护只接受固定目标；MaixCam终止脚本验证PID、存活状态和 `/proc/<pid>/cmdline`归属。强杀需要 `--force`和确认；ESP32重启在代码层保持拒绝。
- L1共68项测试通过：协议4项、ESP32 30项、MaixCam 18项、CLI 16项；CLI源码无缓存编译、VS Code 46个任务JSON、正式源码语言和Git格式检查通过。
- L2确认ESP32 TCP 8266、MaixCam SSH、设备RTSP、本机RTSP和WebRTC均在线；本机中继重启后通过H.264实际解码，1280×720、20 fps，首帧1.672秒。
- 本轮没有登录ESP32 REPL、上传设备源码、复位ESP32、停止/强杀MaixCam视频、重启设备或产生任何底盘/机械臂运动。

## 未解决事项

- MaixCam同次开机内摄像头重新初始化失败和重启后 `num`占用仍是设备约束；CLI提供明确反馈与维护入口，但不自动杀非项目进程。
- `robot reboot maixcam`和真实MaixCam `stop/restart/kill`本轮只通过命令路由、确认和假执行器测试，未在真机执行破坏性验收。
- `robot reboot esp32`保持锁定，必须等安全运行时部署并按L3安全门验证后再开放。
- CLI当前管理ESP32、MaixCam和视频；机械臂连接适配器待TCP232与LAN1参数确认后追加。

## 经验信号（供人工审阅）

- 候选信号：Windows父进程捕获输出时，后台媒体子进程可能继承管道并让一次性CLI无法退出；使用临时文件承接外部命令输出可避免等待管道EOF。本目标只记录事实，不创建经验文档。

## 提交意图

```text
feat: add flat robot connection CLI
```
