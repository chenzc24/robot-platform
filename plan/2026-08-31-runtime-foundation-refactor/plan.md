# 重构本地运行时基础与VS Code入口

- 状态：`completed`
- 负责人：Agent本地实施，用户稍后另行真机验收
- 最高验证等级：`L1`

## 目标

在不连接、部署或驱动任何真实设备的前提下，将当前ESP32和MaixCam占位程序整理为可扩展的英文源码基础：保留已验证安全核心，增加模块边界、结构化状态与错误反馈、资源所有权和控制租约等保护原语，并扩充安全的VS Code检查、测试、状态和日志入口。

`src/esp32/legacy/` 是字节级历史快照，中英混合内容保持原样。项目设计和操作文档可继续使用中文；新增运行代码、注释、docstring、日志键、状态和错误码统一使用英文。

## 工作区初始状态

```text
## main...origin/main
 M .vscode/settings.json
```

`.vscode/settings.json` 是用户已有的MicroPython按钮修改，属于本目标只读路径。本目标通过 `.vscode/tasks.json` 扩充可调用入口，不覆盖、暂存或提交该设置文件。

## 可修改文件

- `src/esp32/app/`
- `src/maixcam/app/`
- `src/maixcam/video/`
- `protocol/`
- `tests/esp32/`
- `tests/maixcam/`
- `tests/protocol/`
- `tools/dev/`
- `.vscode/tasks.json`
- `README.md`
- `docs/overall-plan.md`
- `docs/runtime-foundation.md`
- `docs/esp32/`、`docs/maixcam/` 中与本地运行时边界直接相关的文档
- `src/esp32/README.md`、`src/maixcam/README.md`
- `plan/2026-08-31-runtime-foundation-refactor/plan.md`
- `plan/log.md`
- Git忽略的Python缓存目录（仅本地安全清理）

## 只读文件和目录

- `.vscode/settings.json`
- `src/esp32/legacy/`
- `ESP32/`、`Camera/`、`Robot Arm_Claws/`
- 本地 `secrets.py`、`device_config.py`和所有真实凭据
- MaixCam、ESP32、TCP232和机械臂设备文件系统与当前进程

## 共享依赖

- ESP32 `SafeMecanumChassis` 和 `MotorBus` 的现有22项回归测试。
- MaixCam RTSP已验证的1280×720、20 fps、2 Mbps默认参数和UART0默认监听器释放规则。
- `protocol/runtime-status.schema.json` 将成为ESP32、MaixCam和后续控制台的共享状态契约。
- 不在本目标中确定机械臂命令协议、UART引脚、TCP232参数或底盘远程运动协议。

## 风险和安全门

- 风险：跨ESP32和MaixCam的共享状态契约发生变化；本地代码结构变更但未经真机验证。
- 设备：不需要；禁止SSH、SCP、WebREPL、mpremote、上传、复位、摄像头启停和CAN访问。
- 用户操作：本轮无；稍后另建L2/L3目标验证。
- 备份和恢复：Git保留当前受控版本；现有设备备份和设备部署均不改动。
- 运动确认：不适用，本轮不运行真实运动代码。

## 预期工作

1. 定义轻量、MicroPython兼容的运行时状态与错误契约。
2. 保留ESP32安全状态机与CAN帧实现，增加应用生命周期、状态快照、传输计数和独立控制租约保护原语。
3. 将MaixCam RTSP占位程序拆分为CLI、可注入视频服务、资源所有权和结构化状态，保留原有参数和启停脚本入口。
4. 增加契约、安全、状态、资源与故障回滚测试。
5. 新增不产生运动的VS Code本地检查、组合测试、连接状态、日志和媒体状态入口。
6. 更新模块边界、状态契约、未部署边界和后续真机验收要求。

## 验证

- 新增与既有Python单元测试，包括故障注入和结构化状态契约。
- Python静态编译、PowerShell解析和VS Code JSON解析。
- 新增正式源码的非ASCII扫描，排除只读 `legacy/`、本地秘密值和用户 `.vscode/settings.json`。
- 秘密、凭据、当前DHCP地址、缓存和原始资料扫描。
- `git diff --check`
- `git status --short --branch`

L1覆盖本地契约、模块、故障保护与工具入口。MaixPy实际资源、MicroPython导入、设备部署和行为一律记为未执行，待用户上机时另建目标。

## 实际结果

- 新增版本化运行时状态Schema，并由ESP32和MaixCam两套轻量实现共同遵守；事件、设备、子系统和错误码在发出前验证命名规则。
- ESP32入口拆为应用生命周期、状态输出和控制租约；底盘状态机与MotorBus增加可观测快照和发送计数，默认入口仍不初始化运动硬件。
- MaixCam视频入口拆为CLI、可注入服务、MaixPy后端和资源所有权；启停脚本增加PID归属、启动就绪事件、超时和只读状态检查。
- VS Code形成41个任务入口，新增统一本地预检、三组测试、工作区验证、实时链路检查、视频状态/日志/电脑中继状态和开发会话组合任务；用户的 `.vscode/settings.json` 保持原样。
- 新增运行时边界文档，并同步总体、ESP32和MaixCam文档。所有本轮正式源码、注释、事件和错误码均为英文，中文保留在设计与安全文档中。
- L1共52项测试通过：共享协议4项、ESP32 30项、MaixCam 18项；18个正式Python源文件通过无缓存编译，本地秘密和设备覆盖文件未被读取；Bash语法、PowerShell解析、VS Code JSON、共享Schema和源码语言检查通过。
- 本轮没有连接、上传、重启或驱动任何真实设备，现有设备部署版本未改变。

## 未解决事项

- 新模块尚未在MicroPython 1.27.0或MaixCam真机上导入、部署和启停；用户上机后需另建L2目标逐设备验证，不能把本地通过写成真机通过。
- ESP32 `ControlLease` 尚未连接底盘本地停车/失能；机械臂协议、UART/TCP232和统一任务状态仍不在本目标范围。
- MaixCam画面顺时针90°旋转、视觉识别和最终控制台仍需后续目标。
- 4个Git忽略的历史 `__pycache__` 目录仍在本机；删除操作被当前本机执行策略拒绝。它们不会进入Git，新的本地预检和测试均设置为不生成字节码缓存。

## 经验信号（供人工审阅）

- 候选信号：Python编译缓存可能保留已删除本地配置的字节码，后续可考虑把“清理缓存且禁止测试再生成缓存”固化为人工维护规则。本目标只记录事实，不创建经验文档。

## 提交意图

```text
refactor: establish modular device runtime foundation
```
