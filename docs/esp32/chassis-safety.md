# ESP32底盘安全核心

- 实现位置：`src/esp32/app/main.py`、`application.py`、`chassis_control.py`、`control_lease.py`
- 当前验证：L1假MotorBus，不连接CAN或真实电机
- 部署状态：未部署；历史真机程序继续运行

## 1. 默认安全入口

正式 `main.py` 当前只支持 `safe_idle`：

```text
配置缺失 ─┐
未知模式 ─┼─→ SAFE_IDLE → 不初始化CAN、电机、UART或舵机
ps2/idle ─┘    （这些模式尚未迁移，因此也被拒绝）
```

只有完整实现并通过相应安全验证的模式才能加入 `SUPPORTED_RUN_MODES`。历史程序中“非ps2即执行运动示例”的回退路径不进入正式应用。

## 2. 底盘状态机

```text
DISABLED
   │ enable_motors()
   ▼
ENABLING ──任何异常──→ FAULT
   │
   ▼
ENABLED_STOPPED ←── stop()/零速度 ── MOVING
   │                                  ▲
   └──────── 非零drive() ─────────────┘

任意正常状态 ── disable() ──→ DISABLED
任意总线异常 ── 尽力停车+失能 ──→ FAULT
```

状态规则：

- 只有 `DISABLED` 可以进入使能流程。
- 使能前先失能全部电机并写零目标；驱动初始化后再次写零目标。
- 只有 `ENABLED_STOPPED` 和 `MOVING` 接受运动命令。
- `DISABLED`、`ENABLING` 和 `FAULT` 的运动命令被拒绝，不向总线写速度。
- `stop()` 每次都调用 `stop_all()`，不依据软件缓存跳过。
- `disable()` 先写零目标，再失能全部电机。
- 总线操作中途异常会记录原异常，尽力调用 `stop_all()` 和 `disable_all()`，状态保持 `FAULT`。

## 3. 速度和输入约束

- 车体线速度向量限制为0.60 m/s。
- 车体角速度限制为0.80 rad/s。
- 四轮目标按200 RPM等比例归一化，保持运动方向比例。
- NaN、正负无穷和非正加速度在任何速度写入前被拒绝。
- 接近零的四轮目标转为明确的 `stop_all()`。

以上参数沿用历史代码，只说明软件限幅已经存在，不代表这些数值已通过真实底盘安全验收。

## 4. MotorBus契约

安全核心通过依赖注入使用以下接口：

```text
prepare_speed_mode(motor_ids)
set_acc(motor_id, acc_rad_s2)
set_speed(motor_id, speed_rad_s)
stop_all(motor_ids)
disable_all(motor_ids)
```

正式 `MotorBus` 和假CAN帧测试已经在独立目标中实现，并验证使能前后清零、批量失败继续和初始化回滚；详见 [`motor-can.md`](motor-can.md)。目前仍未实现ACK与驱动状态读取，因此状态机只知道“调用没有抛出异常”，不能宣称真实驱动器已执行命令。

`SafeMecanumChassis.status_snapshot()` 现可返回状态、四轮目标和最后错误；`MotorBus.status_snapshot()` 返回发送帧数、发送失败和ACK尚不可用的明确标志。

`ControlLease` 已实现单控制者、有界超时、续租和释放规则，但仍是硬件无关原语。租约过期触发真实停车和失能尚未接入，不得把它表述为已完成的心跳停车。

## 5. 自动化验证

在VS Code运行：

```text
ESP32: Run safety tests
```

或在终端运行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests\esp32 -p "test_*.py" -v
```

原有12项底盘状态机测试仍全部保留；新增测试另外覆盖运行时状态、状态快照、CAN发送计数与控制租约。底盘状态机基线覆盖：

- `SAFE_IDLE`未知模式回退。
- 初始禁用状态下 `stop()` 仍发送零目标。
- 失能状态拒绝 `drive()`。
- 使能前后零目标调用顺序。
- 非禁用状态拒绝重复使能。
- 有效运动状态转换和四轮限幅。
- 零速度显式停车。
- 失能后再次拒绝运动。
- 使能失败进入 `FAULT` 并尝试停车失能。
- 运动写入失败进入 `FAULT` 并尝试停车失能。
- 失能失败保持 `FAULT`。
- 非有限输入在速度写入前被拒绝。

## 6. 尚未覆盖

- MicroPython CAN构造、真实CAN收发和驱动器反馈。
- PS2接收、250毫秒失联停车和控制权管理。
- Camera UART、网络控制、传感器、循迹和舵机。
- 真实电机的使能、停车、失能与断链行为。

这些内容必须分目标迁移并逐级验证；本文件的L1结果不能替代L2连接或L3运动安全门。
