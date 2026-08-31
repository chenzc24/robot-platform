# 建立ESP32 MicroPython开发基线

- 状态：`completed`
- 负责人：Agent实施，用户负责后续设备接入
- 最高验证等级：`L1`

## 目标

在不连接和不写入真机的前提下，建立 `VS Code + Python/Pylance + MicroPython + mpremote + esptool + WebREPL` 的ESP32本地开发基线，且不安装ESP-IDF。

## 工作区初始状态

```text
## main...origin/main
```

工作区干净。检测到Python 3.12和3.13；本目标选用Python 3.12。串口枚举只返回COM3至COM6蓝牙虚拟串口，没有确认ESP32设备，本目标不进行L2真机连接。

## 可修改文件

- `.gitignore`
- `.vscode/`
- `README.md`
- `docs/overall-plan.md`
- `requirements-dev.txt`
- `src/esp32/`
- `docs/esp32/`
- `plan/2026-08-31-esp32-development-baseline/plan.md`
- `plan/log.md`

## 只读文件和目录

- `AGENTS.md`
- `docs/network/`
- `ESP32/`
- `Camera/`
- `Robot Arm_Claws/`
- `tmp/`

## 共享依赖

- 已冻结的MicroPython方案：ESP32业务代码不迁移C/C++，日常不使用ESP-IDF SDK或扩展。
- `docs/network/README.md` 中的手机热点、WebREPL和安全边界。
- 当前本地自定义固件 `ESP32/MicroPython1.27.bin`，本目标只读且不烧录。

## 风险和安全门

- 风险：本地工具安装和VS Code配置；不访问设备，不产生运动。
- 设备：不需要。
- 用户操作：后续L2目标再连接ESP32 USB并操作BOOT/RST。
- 备份和恢复：本目标不写设备；未来刷写前必须先备份设备文件系统并记录芯片和固件信息。
- 运动确认：不适用。

## 预期工作

1. 建立Python 3.12虚拟环境并安装官方 `mpremote`、`esptool`。
2. 在本机安装官方WebREPL客户端，并记录其来源和版本。
3. 建立VS Code推荐扩展、解释器设置和安全的USB/Wi-Fi任务入口。
4. 建立 `src/esp32/` 的安全最小应用、配置约定和开发说明。
5. 验证工具可执行、Python文件可编译、JSON配置有效且资料目录仍被忽略。

## 验证

- `git diff --check`
- `git status --short --branch`
- `.venv/Scripts/python.exe -m mpremote --version`
- `.venv/Scripts/python.exe -m esptool version`
- `.venv/Scripts/python.exe -m compileall src/esp32`
- 解析 `.vscode/*.json` 和工具链锁定文件。
- `git check-ignore` 复核资料、秘密配置、虚拟环境和本地工具目录。

本目标最高为L1，只验证本地工具和安全最小Python代码；不把未执行的USB或Wi-Fi真机测试写成通过。

## 实际结果

- 已建立Python 3.12虚拟环境，安装并验证 `mpremote 1.29.0` 和 `esptool 5.3.1`；`pip check` 无依赖错误。
- 已在本机 `.tools/webrepl` 安装官方WebREPL客户端并固定来源提交 `1e09d9a1d90fe52aba11d1e659afbc95a50cf088`。
- 已建立VS Code推荐扩展、解释器设置以及无设备、USB读取、USB文件、USB REPL和WebREPL任务；未实现自定义传输协议。
- 已建立 `src/esp32/app` 安全最小应用、无秘密配置模板和开发说明，并将正式源码路径固定为 `src/esp32/`。
- 三个VS Code JSON文件解析通过，ESP32 Python源码和官方WebREPL客户端均通过Python编译检查。
- 本地固件首个镜像头经 `esptool image-info` 识别为ESP32-S3、8 MB、DIO、80 MHz，校验有效，构建信息为ESP-IDF `v5.4.2-dirty`。
- `git check-ignore` 确认虚拟环境、本地工具、三个资料目录以及ESP32秘密/本地配置均被忽略。
- 未连接、读取、写入或驱动真实ESP32设备。

## 未解决事项

- 尚未确认实际ESP32 USB端口、板型和设备文件系统内容。
- 尚未备份设备文件系统或读取设备上运行的MicroPython版本。
- 本地固件的完整镜像布局和目标烧录地址仍需结合设备及供应方说明确认。
- 手机热点、WebREPL密码设置和无线文件传输留到下一L2目标。

## 经验信号（供人工审阅）


## 提交意图

```text
build: establish ESP32 MicroPython development baseline
```
