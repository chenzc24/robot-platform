# ESP32 MicroPython source

这是ESP32底盘正式源码目录。根目录下的 `ESP32/` 是被Git忽略的原始资料库；不要从本目录反向覆盖资料原件。

## 当前状态

`app/` 包含已验证的Wi-Fi/WebREPL启动模块，以及不会初始化电机、CAN或UART的安全最小 `main.py`。设备上现有的底盘 `main.py` 尚未迁入本目录，不能用安全最小文件直接覆盖；现有底盘程序将在单独目标中审计和迁移。

设备备份中的现有底盘程序已原样纳入 `legacy/chassis_2026_08_31/`。该目录是字节级历史快照，不是部署源；静态审计发现未知运行模式自动运动、失能后仍可写速度目标等阻断问题。详见 [`../../docs/esp32/legacy-chassis-audit.md`](../../docs/esp32/legacy-chassis-audit.md)。

## 本地检查

在VS Code中运行：

```text
Tasks: Run Task
→ ESP32: Check Python sources
```

或者：

```powershell
.\.venv\Scripts\python.exe -m compileall -q src\esp32\app
```

USB和WebREPL任务见 [`../../docs/esp32/development.md`](../../docs/esp32/development.md)。
