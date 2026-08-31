# ESP32 MotorBus与CAN帧适配器迁移

- 状态：`completed`
- 负责人：Agent执行
- 最高验证等级：`L1`

## 目标

从冻结历史快照选择性迁移电机CAN速度模式协议，形成可向安全底盘状态机注入的正式 `MotorBus`。使用假CAN验证29位扩展ID、8字节载荷、小端参数编码、速度限幅、使能前后零目标、四电机批量失败继续和异常回滚。本目标不构造MicroPython真实CAN、不连接或部署ESP32。

## 工作区初始状态

```text
## main...origin/main
```

工作区干净。正式底盘安全状态机和12项假MotorBus测试已提交；真实设备仍运行历史PS2程序。

## 可修改文件

- `src/esp32/app/motor_bus.py`
- `tests/esp32/test_motor_bus.py`
- `docs/esp32/motor-can.md`
- `docs/esp32/chassis-safety.md`
- `docs/esp32/development.md`
- `docs/esp32/legacy-chassis-audit.md`
- `src/esp32/README.md`
- `plan/2026-08-31-esp32-motor-can-adapter/plan.md`
- `plan/log.md`

## 只读文件和目录

- `src/esp32/legacy/`
- 其余 `src/esp32/app/` 文件
- `.vscode/tasks.json` 和既有测试
- ESP32设备、文件系统、原始资料和设备备份

## 共享依赖

- `SafeMecanumChassis` 需要的MotorBus五个接口。
- 历史CAN协议：29位扩展ID、主机ID `0xFD`、速度模式参数索引和小端载荷。
- 历史驱动速度硬上限44 rad/s及默认速度PI/滤波值。
- 当前L1结果不能证明CAN收发、驱动ACK或真实电机状态。

## 设计边界

- CAN对象通过构造参数注入；正式模块不直接导入或构造 `esp32.CAN`。
- 所有帧必须严格验证电机ID、通信类型、参数索引和8字节载荷。
- 单电机初始化在使能前和使能后都写零速度。
- 批量停车/失能即使某一帧失败也继续尝试其余电机，最后重新抛出首个异常。
- 批量初始化失败后尽力停车并失能全部目标电机。
- `CAN.send()` 返回 `False` 视为发送失败；`None` 与其它正常返回值兼容当前MicroPython API。
- 不把“帧已发送”解释为“驱动已执行”；ACK与状态反馈留待后续协议确认。

## 预期工作

1. 实现CAN扩展ID、参数载荷和MotorBus基础命令。
2. 实现安全的单/多电机速度模式初始化、停车和失能。
3. 使用假CAN覆盖帧向量、限幅、调用顺序、发送失败和批量回滚。
4. 增加MotorBus—SafeMecanumChassis集成测试。
5. 更新设计、开发、审计和源码入口文档。

## 验证

- `python -m unittest discover -s tests/esp32 -p "test_*.py"`
- `python -m compileall -q src/esp32/app tests/esp32`
- 固定CAN帧测试向量与小端浮点/整数断言。
- 假CAN注入失败后的其余电机尝试和回滚断言。
- 秘密扫描、`git diff --check`、`git status --short --branch`。

## 实际结果

- 新增可注入CAN对象的正式 `MotorBus`，实现严格29位扩展ID、固定8字节载荷、uint32/float32小端参数写入、有限数校验和±44 rad/s驱动侧限幅。
- 单电机初始化在使能前后写零速度；批量停车和失能在单帧失败后继续处理其余电机；批量初始化失败时尽力停车并失能完整目标集合。
- 新增10项FakeCAN测试，并与既有12项底盘安全核心测试共同运行；22项全部通过。源码与测试静态编译通过。
- 新增CAN适配器设计文档，并同步更新底盘安全、开发入口、历史审计和源码入口说明。
- 完成秘密、差异格式和提交范围检查；本轮没有连接、写入或驱动任何真实硬件。

## 未解决事项

- 尚未用驱动器官方资料确认历史参数索引、默认PI/滤波值和反馈帧。
- 尚未构造真实MicroPython CAN，CAN引脚、1 Mbps波特率、发送返回语义和bus-off恢复均未验证。
- 尚无ACK、驱动状态、故障码、实际速度或真实回滚结果；“发送成功”不能解释为“驱动已执行”。
- 下一目标应先完成协议资料核对，再设计不使能电机的L2 CAN连接检查；任何真实使能或运动仍须建立L3目标并重新通过人工安全门。

## 经验信号

- CAN发送侧帧一致性与驱动执行确认必须作为两个独立验证层；FakeCAN只能关闭前者，不能替代ACK和状态反馈。

## 提交意图

```text
feat: add tested ESP32 motor CAN adapter
```
