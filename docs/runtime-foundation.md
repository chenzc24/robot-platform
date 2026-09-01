# 设备运行时基础

- 状态：本地L1基线，未部署真机
- 适用：ESP32安全应用、MaixCam视频服务和后续设备服务
- 共享契约：`protocol/runtime-status.schema.json`

## 1. 语言与边界

- 新增运行代码、注释、docstring、标识符、日志键、事件名和错误码使用英文。
- 项目设计、现场操作和安全文档可使用中文。
- `src/esp32/legacy/` 是字节级历史快照，不翻译、不格式化、不作为部署源。
- 本地 `secrets.py`、`device_config.py`和编译缓存不进入Git，工作区验证工具不读取秘密文件内容。

## 2. 结构化状态契约

ESP32、MaixCam和后续控制台共享下列必填字段：

```json
{
  "schema_version": 1,
  "event": "service_ready",
  "device": "maixcam",
  "subsystem": "video",
  "state": "ready",
  "sequence": 2,
  "uptime_ms": 1250,
  "error_code": null,
  "detail": {}
}
```

服务生命周期状态为：

```text
starting / idle / ready / running / stopping / stopped
disconnected / safe_idle / fault / estop
```

这些是服务健康和安全状态，不等于未来机器人任务的 `ARMED/RUNNING/COMPLETED` 业务状态。两者必须使用不同字段，避免把“服务正在运行”误解为“运动任务正在执行”。

## 3. ESP32模块

| 模块 | 职责 | 当前硬件行为 |
|---|---|---|
| `main.py` | 组合入口 | 无 |
| `application.py` | 运行模式门禁和生命周期 | 仅 `SAFE_IDLE` |
| `esp_runtime_status.py` | MicroPython兼容的JSON状态事件 | 无 |
| `control_lease.py` | 单控制者、有界超时、续租和释放 | 无，尚未连接底盘停车 |
| `chassis_control.py` | 底盘状态机、限幅和故障回滚 | 通过注入MotorBus才可发生 |
| `motor_bus.py` | CAN帧编码、发送、失败计数和批量回滚 | 通过注入CAN才可发生 |

`ControlLease` 当前只是已测试的保护原语。在正式底盘服务完成前，租约过期不会自动调用真实停车，不得宣称心跳停车已实现。

## 4. MaixCam视频模块

```text
rtsp_server.py        CLI、信号和进程生命周期
  └─ video_service.py
       ├─ RtspVideoService      状态、回滚与摄像头所有权
       └─ MaixRtspBackend       MaixPy摄像头与RTSP薄适配器

maix_runtime_status.py                  结构化状态
resource_guard.py                       进程内资源独占
start.sh / stop.sh / status.sh          PID归属验证与运行入口
```

保护规则：

- 导入CLI和服务模块不导入 `maix`，因此不会在本地测试时占用UART或摄像头。
- 只有 `MaixRtspBackend` 构造时导入 `maix`，并立即释放系统默认UART0监听器。
- 视频服务必须成功获得 `camera` 所有权后才创建后端。
- 启动或停止异常时释放所有权、记录稳定错误码并进入 `fault`。
- Shell脚本在发送终止信号前检查PID是否确实属于本项目RTSP程序。

## 5. VS Code入口

本轮只修改 `.vscode/tasks.json`，不改用户未提交的 `.vscode/settings.json` 按钮配置。

新增的主入口：

- `Robot: Local preflight`：无设备语法、工作区、契约和全部单元测试。
- `Robot: Run all local tests`：ESP32、MaixCam和共享契约测试。
- `Robot: Check live links`：用户稍后手动运行，只检查ESP32 WebREPL端口和MaixCam SSH。
- `MaixCam Video: Start development session`：上传、启动、电脑中继和实际帧探测；运行前仍需人工退出 `num`。
- `MaixCam Video: Status`、`Show recent log`、`PC relay status`：分层诊断。
- `Robot: Stop PC services`：只停止电脑侧FFmpeg和MediaMTX，不停止设备RTSP。

扁平日常入口新增：

- `Robot: Connect`：发现两台设备，启动缺失的MaixCam RTSP和电脑中继，健康服务保持不动。
- `Robot: Status`：只读三级摘要。
- `Robot: Details`：展开全部检查、错误码和下一步建议。
- `Robot: Disconnect`：只停止电脑中继。

这些任务调用仓库根目录的 `robot.cmd`。同一CLI还提供受保护的 `ps/logs/stop/restart/kill/reboot`维护命令，但不提供任意PID强杀；ESP32重启在安全运行时真机验收前保持锁定。

本轮不添加电机使能、底盘速度或机械臂动作快捷入口。

## 6. 验收边界

本轮只可确认：

- 共享状态字段和设备实现在本地测试中一致。
- ESP32安全入口仍不初始化运动硬件。
- 控制租约、摄像头所有权、状态反馈和故障回滚通过假对象测试。
- 新部署清单和脚本尚未在MicroPython或MaixCam真机上执行。

用户上机后必须另建L2目标，先验证导入、文件部署、结构化日志、摄像头启停和恢复；未通过L2前不部署ESP32运动模式。
