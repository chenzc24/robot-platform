# ESP32 MicroPython开发环境

- 状态：USB恢复通道、手机热点自动接入和WebREPL已完成L2验证
- 运行方式：MicroPython
- IDE：VS Code + Python + Pylance
- 不需要：ESP-IDF SDK、ESP-IDF VS Code扩展、C/C++迁移

## 1. 工具边界

| 工具 | 作用 | 是否写设备 |
|---|---|---|
| VS Code / Pylance | 编辑和检查Python源码 | 否 |
| `mpremote` | USB枚举、文件、REPL、运行和软复位 | 视具体命令而定 |
| `esptool` | 芯片信息、固件检查、固件烧录 | 读取命令不写；烧录命令会写 |
| `webrepl.html` | Windows上的官方WebREPL终端和单文件传输 | 上传时写设备文件系统 |
| MicroPython | ESP32上的固件和Python运行时 | 运行于设备 |

ESP-IDF位于MicroPython固件底层。只有编译自定义MicroPython固件或增加C/C++原生模块时才安装ESP-IDF；日常Python开发不需要它。

## 2. 本机环境

项目固定使用Python 3.12虚拟环境：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

当前直接依赖：

```text
mpremote 1.29.0
esptool 5.3.1
```

基线建立时COM3至COM6均为蓝牙虚拟串口；首次真机联调新增了目标设备COM7。

首次真机联调后，目标设备固定识别为COM7上的WCH CH340串口桥。MicroPython运行时信息：

```text
MicroPython 1.27.0（2026-05-11）
Board: ESP32_GENERIC_S3-SPIRAM_OCT
Runtime: MicroPython / GIL
```

设备文件系统已只读备份到本机忽略目录 `device-backups/esp32/20260831-111429/`：22个文件，共125684字节。根目录和 `SmartHybridChasisDemo/` 各有一套相同的11个程序文件，逐文件SHA-256一致。根目录 `robot_config.py` 当前为 `RUN_MODE="ps2"`；根目录 `main.py` 会初始化CAN和电机并进入PS2控制循环，因此任何后续复位仍须保持底盘安全。

开发网络已通过2.4 GHz手机热点验证。ESP32能在重启后自动取得DHCP地址并启动WebREPL；本轮地址为 `10.114.1.97`，该地址不是固定配置，热点重新分配后应以手机客户端列表或串口 `WLAN.ifconfig()` 为准。电脑与ESP32之间的ICMP和TCP 8266均已验证。

WebREPL客户端来自官方仓库：

```text
https://github.com/micropython/webrepl.git
commit 1e09d9a1d90fe52aba11d1e659afbc95a50cf088
```

新电脑可以安装到本地忽略目录：

```powershell
git clone https://github.com/micropython/webrepl.git .tools\webrepl
git -C .tools\webrepl checkout 1e09d9a1d90fe52aba11d1e659afbc95a50cf088
```

`.venv/` 和 `.tools/` 不进入Git。

## 3. VS Code任务

通过 `Terminal → Run Task` 使用任务。

### 无设备任务

- `ESP32: Check Python sources`
- `ESP32: Run safety tests`
- `ESP32: Tool versions`
- `ESP32: Inspect local firmware image`

### USB读取任务

- `ESP32: List USB devices`
- `ESP32: Read chip info (USB, no write)`
- `ESP32: USB file tree`（使用 `mpremote fs tree -vh`）
- `ESP32: USB download one file`

### USB写入或运行任务

- `ESP32: USB upload one file`
- `ESP32: USB soft reset`
- `ESP32: USB REPL`

### Wi-Fi任务

- `ESP32: Open WebREPL browser client`

该任务打开固定版本的官方 `webrepl.html`。在页面中输入当前设备地址，例如 `ws://10.114.1.97:8266/`，再手动输入本机保存的WebREPL密码。页面同时提供交互终端和单文件上传；它只允许一个活动连接，上传前应关闭其他WebREPL连接。

固定版本的 `webrepl_cli.py` 在Windows交互模式下依赖Unix `termios`，而且会在状态行回显已输入的密码，因此不作为VS Code任务暴露。脚本仍保留在本机官方工具目录，后续只有在上游修复或增加不泄密的薄封装后才用于日常命令行部署。

## 4. 为什么没有“一键刷固件”任务

本基线故意不提供擦除和写入Flash的VS Code任务。在第一次连接真实设备前，以下信息尚未确认：

- 实际ESP32-S3板型、Flash容量和串口。
- 当前设备文件系统内容和可恢复备份。
- `MicroPython1.27.bin` 的准确镜像类型及烧录地址。
- BOOT/RST进入下载模式的方法。

完成备份和只读识别后，再根据验证结果增加一个参数明确、需要人工确认的烧录任务。禁止把 `erase-flash` 作为普通开发快捷操作。

已使用 `esptool image-info` 对本地 `ESP32/MicroPython1.27.bin` 进行只读检查：首个镜像头识别为ESP32-S3、8 MB Flash、DIO、80 MHz，校验和与哈希有效，构建信息为ESP-IDF `v5.4.2-dirty`。该结果尚不能单独证明完整合并镜像的目标烧录地址，因此仍不创建写Flash任务。

## 5. 已完成的首次真机接入

1. COM7已确认是目标ESP32-S3，USB芯片信息和MicroPython运行时已读取。
2. 原设备文件系统已完成只读备份，本地固件镜像只做了格式检查，没有刷写或擦除Flash。
3. `network_boot.py`、本机忽略的 `secrets.py` 和新的 `boot.py` 已按可恢复顺序上传。
4. ESP32硬复位后自动连接热点、恢复WebREPL，并通过局域网登录和只读REPL探针。
5. 验证结束后再次硬复位，让设备重新进入原有PS2启动流程；复位后的网络引导和WebREPL端口正常。本轮没有发送运动命令，也没有替换或进入设备上的 `main.py` 再做运行态检查。

以上属于L2设备联调。WebREPL进入交互REPL时可能中断正在运行的 `main.py`，完成调试后必须复位并确认应用恢复。任何可能触发底盘动作的程序必须另行进入L3目标，并执行人工运动安全门。

## 6. 源码和秘密配置

```text
src/esp32/
├── README.md
└── app/
    ├── boot.py
    ├── network_boot.py
    ├── main.py
    ├── device_config.example.py
    └── secrets.example.py
```

使用时在本地复制：

```text
device_config.example.py → device_config.py
secrets.example.py       → secrets.py
```

`device_config.py` 和 `secrets.py` 被Git忽略。热点名称、密码和WebREPL密码不得写入示例、VS Code任务、日志或提交。

设备启动顺序为：

```text
boot.py → network_boot.start()
        → 读取本地secrets.py
        → 限时连接Wi-Fi
        → 启动WebREPL
        → 无论网络成功或失败都继续进入设备原有main.py
```

网络模块不初始化CAN、电机、UART或舵机。Wi-Fi失败会在约20秒后超时，不会阻止底盘应用继续启动。设备上的原始 `boot.py` 可从忽略目录中的完整备份恢复。

## 7. 正式控制与WebREPL分离

```text
开发部署：VS Code → WebREPL → ESP32文件系统/REPL
正式控制：统一控制台 → 控制协议 → ESP32底盘服务
```

WebREPL不是底盘正式控制协议。发布模式应关闭或限制WebREPL，关闭后不能影响底盘心跳、停车、状态和控制服务。

## 8. 现有底盘程序的版本化状态

设备备份中的11个底盘Python文件已原样保存到 `src/esp32/legacy/chassis_2026_08_31/`，并逐文件验证SHA-256。该目录只用于追溯和选择性迁移，不能直接部署。

静态审计见 [`legacy-chassis-audit.md`](legacy-chassis-audit.md)。其中未知运行模式自动执行运动示例、失能后仍允许写入非零速度、导入即初始化硬件和循迹失联不停车属于后续迁移前的阻断项。

第一批选择性迁移已建立默认 `SAFE_IDLE` 和硬件无关底盘状态机，设计及12项假MotorBus回归测试见 [`chassis-safety.md`](chassis-safety.md)。这部分尚未接入CAN或部署设备。
