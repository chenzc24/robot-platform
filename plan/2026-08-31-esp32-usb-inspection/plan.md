# ESP32 COM7只读识别

- 状态：`completed`
- 负责人：Agent执行，用户现场确认
- 最高验证等级：`L2`

## 目标

通过COM7对已连接设备执行只读芯片识别，确认其是否为目标ESP32，不擦除、不烧录、不修改文件系统。

## 工作区初始状态

```text
## main...origin/main
```

工作区干净。Windows已将COM7识别为状态正常的WCH CH340 USB串口桥，VID:PID为 `1A86:7523`；COM3至COM6均为蓝牙虚拟串口。

## 可修改文件

- `plan/2026-08-31-esp32-usb-inspection/plan.md`
- `plan/log.md`

## 只读文件和目录

- 其余全部仓库文件
- ESP32设备Flash和文件系统

## 共享依赖

- `.venv` 中已验证的 `esptool 5.3.1`。
- VS Code开发基线将目标串口作为运行时输入，不在共享配置中写死。

## 风险和安全门

- 风险：打开串口可能通过DTR/RTS复位ESP32，复位后设备可能重新运行已有程序。
- 设备：COM7上的目标设备。
- 用户操作：用户已确认底盘处于安全状态，可以进行本轮串口识别。
- 备份和恢复：本目标不写设备，不需要恢复；文件系统备份属于后续目标。
- 运动确认：用户已于本轮明确确认现场状态。

## 预期工作

1. 运行 `esptool --port COM7 chip-id`。
2. 记录芯片型号、修订版和只读识别结果。
3. 不继续执行Flash写入或文件系统操作。

## 验证

- `.venv/Scripts/python.exe -m esptool --port COM7 chip-id`
- `git diff --check`
- `git status --short --branch`

## 实际结果

- 第一次执行 `esptool --port COM7 chip-id` 能够打开COM7，但ESP下载握手未收到任何串口数据，命令以 `Failed to connect to Espressif device: No serial data received` 结束。
- 用户按BOOT/RST流程手动进入下载模式后，第二次识别成功。
- COM7设备确认为ESP32-S3 QFN56，修订版v0.2，双核+低功耗核、240 MHz、40 MHz晶振、8 MB嵌入式PSRAM，并支持Wi-Fi和Bluetooth LE 5。
- `esptool`将识别stub临时上传到RAM后读取信息，未擦除、烧录或修改设备文件系统，结束时通过RTS硬复位设备。

## 未解决事项

- 尚未通过MicroPython REPL读取设备运行时版本或备份文件系统。
- 尚未读取Flash芯片信息；该读取可与文件系统备份一起纳入下一L2目标。

## 经验信号（供人工审阅）


## 提交意图

```text
docs: record ESP32 USB identification
```
