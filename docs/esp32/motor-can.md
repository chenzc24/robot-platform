# ESP32电机CAN适配器

- 实现：`src/esp32/app/motor_bus.py`
- 测试：`tests/esp32/test_motor_bus.py`
- 当前等级：L1假CAN
- 部署状态：未部署、未连接真实CAN

## 1. 迁移边界

正式 `MotorBus` 从历史 `motor_lib.py` 选择性迁移29位扩展ID、参数写入和速度模式命令。它通过构造参数接收CAN对象，不直接导入或创建 `esp32.CAN`，因此可以先验证协议和失败路径。

```text
SafeMecanumChassis
        │ 五个MotorBus接口
        ▼
     MotorBus
        │ 经过验证的29位扩展帧
        ▼
  注入的CAN对象（当前为FakeCan）
```

历史快照保持不变，正式实现不复用其中“静默补齐载荷”和“遇到首个错误立即停止批量处理”的行为。

## 2. 扩展ID和载荷

29位扩展ID：

```text
bit 28..24：comm_type（5位）
bit 23..8 ：data2 / 主机ID（16位，参数命令使用0x00FD）
bit 7..0  ：motor_id（8位）
```

固定测试向量：

```text
comm_type=0x12, data2=0x00FD, motor_id=1
→ extended_id=0x1200FD01
```

参数写入载荷固定8字节、小端：

```text
byte 0..1：参数索引uint16
byte 2..3：保留0
byte 4..7：uint32或float32参数值
```

示例速度模式帧：

```text
ID      = 0x1200FD01
Payload = 05 70 00 00 02 00 00 00
```

适配器拒绝错误长度、越界ID、越界字节、NaN和无穷，不再自动截断或补齐错误载荷。

## 3. 命令和参数

| 功能 | 通信类型/参数 | 当前约束 |
|---|---|---|
| 使能 | `comm_type=0x03` | 8字节零载荷 |
| 失能 | `comm_type=0x04` | 8字节零载荷 |
| 清故障 | `comm_type=0x04` | 首字节1，其余0 |
| 速度模式 | `0x7005=2` | uint32小端 |
| 速度目标 | `0x700A` | float32，限制±44 rad/s |
| 速度PI | `0x701F/0x7020` | 非负有限数 |
| 速度滤波 | `0x7021` | 0..1 |
| 加速度 | `0x7022` | 正有限数 |

这些索引、默认PI和滤波值继承历史实现，尚未用驱动器官方文档或真实状态读取再次确认。

## 4. 安全调用顺序

单电机速度模式初始化：

```text
失能 → 清故障 → 速度模式 → PI → 滤波 → 加速度
→ 写零速度 → 使能 → 再写零速度
```

批量规则：

- `stop_all()` 即使一个电机发送失败，也继续向剩余电机写零，最后抛出首个异常。
- `disable_all()` 即使停车阶段失败，也继续尝试失能全部电机。
- `prepare_speed_mode()` 任一电机初始化失败后，尽力对整个目标集合执行停车和失能，再重新抛出原异常。
- `CAN.send()` 明确返回 `False` 时视为失败；`None` 被接受以兼容当前MicroPython API。

## 5. L1测试

新增10项假CAN测试，与底盘安全核心12项测试合计22项：

- 29位扩展ID固定向量。
- 速度模式uint32载荷固定向量。
- float32小端编码和44 rad/s驱动限幅。
- ID、载荷、非有限速度和 `CAN.send=False` 拒绝。
- 单电机使能前后零速度顺序。
- `stop_all()` 单帧失败后继续其它电机。
- `disable_all()` 停车失败后仍失能全部电机。
- 批量初始化失败后的全组回滚。
- 正式MotorBus与 `SafeMecanumChassis` 集成后到达 `ENABLED_STOPPED`，最后四帧均为零速度。

运行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests\esp32 -p "test_*.py" -v
```

## 6. 尚未解决

- 真实 `esp32.CAN` 构造、引脚、1 Mbps波特率和发送返回语义。
- 驱动器ACK、状态、故障码、实际速度和使能状态读取。
- CAN总线关闭、bus-off、仲裁失败和重连策略。
- 四个电机部分成功后的真实回滚结果。
- 真实使能、停车和失能行为。

因此当前状态只表示帧编码和软件调用序列正确，不能表示电机执行成功。下一步应先用厂商资料确认协议和反馈帧，再设计不使能电机的L2 CAN连接检查；任何使能或轮子动作仍属于L3。
