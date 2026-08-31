# ESP32安全空闲入口与底盘状态机

- 状态：`completed`
- 负责人：Agent执行
- 最高验证等级：`L1`

## 目标

从历史审计结论出发，在当前 `src/esp32/app/` 建立默认 `SAFE_IDLE` 应用入口和不依赖硬件的底盘安全状态机。确定性修复“未知模式自动运动”“初始停车被缓存跳过”“失能后仍可写速度”和“重新使能前后未清零”四个软件问题，并用假MotorBus回归测试证明。此目标不迁移CAN实现、PS2、传感器、舵机或Camera UART，不连接或部署真机。

## 工作区初始状态

```text
## main...origin/main
```

工作区干净，上一L3 PS2通路测试已完成并提交。设备继续使用现有历史程序，本目标只修改本地正式源码。

## 可修改文件

- `.vscode/tasks.json`
- `src/esp32/app/main.py`
- `src/esp32/app/device_config.example.py`
- `src/esp32/app/chassis_control.py`
- `tests/esp32/`
- `docs/esp32/chassis-safety.md`
- `docs/esp32/legacy-chassis-audit.md`
- `docs/esp32/development.md`
- `src/esp32/README.md`
- `plan/2026-08-31-esp32-safe-chassis-core/plan.md`
- `plan/log.md`

## 只读文件和目录

- `src/esp32/legacy/`
- `src/esp32/app/boot.py`、`network_boot.py`、`secrets.example.py`
- ESP32设备和文件系统
- 原始资料、设备备份和其它子系统

## 共享依赖

- 历史 `MotorBus` 的预期接口：`prepare_speed_mode`、`set_acc`、`set_speed`、`stop_all`、`disable_all`。
- 审计中的C1/C2阻断项和速度限制基线。
- 当前MicroPython兼容目标；正式模块不得依赖CPython专有功能。

## 设计边界

- `SAFE_IDLE` 是缺失、未知或尚未迁移模式的唯一回退，不初始化任何运动硬件。
- 底盘状态至少包括 `DISABLED`、`ENABLING`、`ENABLED_STOPPED`、`MOVING`、`FAULT`。
- 失能时拒绝非零运动目标；`stop()` 每次都向总线发送零目标，不依赖软件缓存跳过。
- 使能顺序必须在驱动初始化前后发送零目标；任何异常进入 `FAULT` 并尽力停车、失能。
- 本目标只提供安全核心和假总线测试，不声称真实驱动反馈或硬件动作已验证。

## 预期工作

1. 为 `main.py` 增加显式运行模式归一化，未知模式回退 `SAFE_IDLE`。
2. 实现底盘状态机、速度限幅、使能/停车/失能和故障回滚。
3. 使用标准库 `unittest` 和假MotorBus覆盖阻断项及错误路径。
4. 增加VS Code测试任务和安全核心文档。
5. 更新历史审计状态，但不改动冻结快照。

## 验证

- `python -m unittest discover -s tests/esp32 -p "test_*.py"`
- `python -m compileall -q src/esp32/app tests/esp32`
- 假MotorBus调用序列断言与状态断言。
- 未知运行模式归一化为 `SAFE_IDLE`。
- 秘密扫描、VS Code JSON解析。
- `git diff --check`
- `git status --short --branch`

## 实际结果

- 正式 `main.py` 只允许 `safe_idle`；配置缺失、非字符串、历史 `ps2`/`idle` 或其它未知值全部归一化为 `SAFE_IDLE`，且不导入运动硬件。
- `device_config.example.py` 明确将 `RUN_MODE` 默认设为 `safe_idle`。
- 新增硬件无关 `SafeMecanumChassis`，实现 `DISABLED`、`ENABLING`、`ENABLED_STOPPED`、`MOVING`、`FAULT` 五态。
- 使能流程按“全部失能—写零—驱动初始化—再次写零”执行；非使能状态拒绝运动；`stop()` 每次向总线写零；`disable()` 写零后失能。
- 运动学保留历史线速度、角速度、轮速和加速度上限，并在总线写入前拒绝NaN、无穷和非正加速度。
- 使能、运动或失能总线异常进入 `FAULT`；使能和运动异常会尽力停车、失能，原异常保留给上层。
- 新增12项标准库 `unittest` 假MotorBus测试，覆盖C1/C2阻断项、正常状态转换、限幅、零速度、重复使能、非有限输入及三类故障路径，全部通过。
- 新增VS Code安全测试任务和独立设计文档；历史快照未修改，并在审计文档中记录为“本地回归已保护、尚未硬件验证”。
- VS Code JSON、Python静态编译、秘密扫描和Git格式检查通过。
- 本轮未连接、写入或驱动ESP32、CAN或电机。

## 未解决事项

- 尚未迁移真实MotorBus/CAN适配器，状态只代表调用未抛异常，不代表驱动已确认执行。
- PS2接收、失联停车、控制权、Camera UART、网络控制、传感器、循迹和舵机均未迁移。
- 尚未在MicroPython运行时执行正式安全核心，也未进行L2/L3验证或部署。

## 经验信号（供人工审阅）

- 执行器安全核心可先通过依赖注入和假总线固定调用顺序、非法状态和故障回滚，再接入真实驱动反馈。

## 提交意图

```text
feat: add ESP32 safe chassis state machine
```
