# ESP32 MicroPython source

这是ESP32底盘正式源码目录。根目录下的 `ESP32/` 是被Git忽略的原始资料库；不要从本目录反向覆盖资料原件。

## 当前状态

`app/` 目前只包含不会初始化电机、CAN、UART或网络的安全最小应用，用于验证编辑、编译和部署通道。现有底盘程序将在单独目标中经过审计后迁入，不能直接整体覆盖到设备。

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
