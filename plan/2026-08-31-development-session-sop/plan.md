# 记录ESP32与MaixCam统一开发会话流程

- 状态：`completed`
- 负责人：Agent记录，用户提供实际画面验收结果
- 最高验证等级：`L0`

## 目标

将已验证的ESP32开发链路、MaixCam开发/视频链路、日常启动与结束顺序、排障分流和已解决/未解决问题写入可发现的操作文档，并补记用户对WebRTC实际画面的验收事实。

## 工作区初始状态

```text
## main...origin/main
 M .vscode/settings.json
```

`.vscode/settings.json` 是用户已有未提交修改，与本文档目标无关；保持只读、不暂存、不提交。

## 可修改文件

- `README.md`
- `docs/development-session.md`
- `docs/maixcam/video.md`
- `plan/2026-08-31-maixcam-rtsp-video/plan.md`
- `plan/2026-08-31-development-session-sop/plan.md`
- `plan/log.md`

## 只读文件和目录

- `.vscode/settings.json`
- 所有运行代码、VS Code任务、设备配置和本地秘密
- `ESP32/`、`Camera/`、`Robot Arm_Claws/`
- ESP32、MaixCam和机械臂设备文件系统

## 共享依赖

- `docs/esp32/development.md`
- `docs/maixcam/development.md`
- `docs/maixcam/video.md`
- 已完成的ESP32 WebREPL与MaixCam SSH/RTSP L2验证事实

## 风险和安全门

- 风险：只记录流程和事实，不改变软件行为、设备状态、网络或自启动。
- 设备：不需要连接或操作设备。
- 用户操作：无。
- 备份和恢复：Git可恢复文档变更。
- 运动确认：不适用。

## 预期工作

1. 创建统一开发会话SOP，明确两条设备链路的日常正常路径。
2. 记录首次搭建遇到的阻塞、当前处理方式和剩余风险。
3. 补记WebRTC实际视频正常及画面需顺时针旋转90°的验收结果。
4. 从项目入口链接SOP，更新事实日志。

## 验证

- 检查Markdown结构、链接和记录之间的事实一致性。
- 确认未写入热点、SSH或WebREPL密码及当前DHCP地址。
- `git diff --check`
- `git status --short --branch`

L0足以覆盖本纯文档目标；不执行设备连接、视频采集或运动验证。

## 实际结果

- 新增 `docs/development-session.md`，记录ESP32开发链路、MaixCam代码/视频链路、公共网络前置条件、日常启动与结束顺序、排障分流、恢复通道和问题状态。
- 项目 `README.md` 已链接该SOP，避免流程只存在于对话中。
- 原视频文档、目标计划和事实日志已补记：用户确认WebRTC实际视频流正常，画面需顺时针旋转90°。
- L0验证通过：文档链接目标存在，未记录当前DHCP地址或私钥，`git diff --check` 通过。本目标未连接或修改任何设备。

## 未解决事项

- ESP32 WebREPL仍需手动填写当前地址和密码，尚无无线原子部署与健康检查。
- MaixCam重启后仍需人工退出 `num`；同一开机会话中摄像头重启可能需要物理重启恢复。
- 视频顺时针旋转90°已记录但未实施。

## 经验信号（供人工审阅）

首次搭建、日常启动和故障恢复混在同一流程时，会显著增加排障分支；可能值得后续提炼为跨设备开发会话模式，但本目标不自动创建经验文档。

## 提交意图

```text
docs: record device development session workflow
```
