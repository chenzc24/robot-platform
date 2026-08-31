# ESP32与MaixCam统一开发会话SOP

- 状态：开发期实施基线
- 范围：电脑、ESP32-S3、MaixCam和手机热点
- 不包含：机械臂运动、底盘运动命令和最终控制台

本文档记录已经真机验证的日常开发路径。首次安装、日常启动和故障恢复必须分开；日常流程不重复刷写固件、安装工具或修改系统配置。

## 1. 两条设备链路

### 1.1 ESP32开发链路

```text
VS Code本地源码
  ├─ USB / mpremote / esptool  → 首次配置、备份和恢复
  └─ Wi-Fi / WebREPL         → 日常文件上传、REPL和重启
                                      ↓
                                ESP32 MicroPython
```

USB是恢复通道，不是日常无线开发的必需条件。WebREPL是开发部署通道，不是最终底盘控制协议。

### 1.2 MaixCam开发与视频链路

```text
代码下行：VS Code → SCP → /root/robot-platform/ → SSH启停/日志

视频上行：MaixCam RTSP/H.264
          → FFmpeg -c:v copy重封装
          → MediaMTX
          → 本机RTSP / HLS / WebRTC
```

SSH/SCP与RTSP是两个相互独立的平面：前者管理代码和进程，后者持续传输视频。

## 2. 日常启动流程

### 2.1 公共网络

1. 开启已配置的2.4 GHz手机热点，关闭自动休眠。
2. 电脑连接热点。
3. 给ESP32和MaixCam上电；如底盘同时供电，必须先确保它处于已失能、架空或其它约定安全状态。
4. 等待两台设备获取DHCP地址。日常不在仓库中记录当前地址。

### 2.2 ESP32

1. 从手机热点客户端列表确认ESP32当前IPv4。
2. 只在需要部署或REPL时，运行 `ESP32: Open WebREPL browser client`。
3. 在官方WebREPL页面输入 `ws://<esp32-ip>:8266/` 和本机保存的密码。
4. 关闭其它WebREPL会话，再上传单个已审阅文件。
5. 进入REPL前假定当前 `main.py` 会被中断；任何复位前都必须考虑设备上的PS2/CAN程序可能重新初始化。
6. 调试结束后断开WebREPL。如执行复位，现场确认原应用恢复且设备仍保持安全状态。

本阶段没有ESP32无线批量上传、原子切换和健康检查的一键流程；不得把手工WebREPL上传表述为已完成的自动部署通道。

### 2.3 MaixCam

1. 运行 `MaixCam: Check SSH`。失败时先排查热点和mDNS，不继续启动媒体工具。
2. MaixCam重启后，在设备屏幕退出自启动的 `num` 应用，释放摄像头。
3. 运行 `MaixCam Video: Start RTSP`；任务会先上传受Git管理的源码，再启动设备RTSP。
4. 运行 `MaixCam Video: Start PC relay`，启动FFmpeg无转码兼容桥和MediaMTX。
5. 运行 `MaixCam Video: Open WebRTC`。
6. 只在画面异常或无画面时，运行 `Probe direct` 和 `Probe relay`缩小故障范围。

当前人工验收结果：WebRTC实际视频流正常；画面最终显示方向应顺时针旋转90°。旋转尚未实施，属于后续显示和坐标系标定目标。

## 3. 日常结束流程

1. 断开ESP32 WebREPL会话，不留互动REPL长期占用运行程序。
2. 运行 `MaixCam Video: Stop PC relay`：先停FFmpeg，再停MediaMTX。
3. 如MaixCam仍保持供电，日常不反复停止并重启RTSP；当前驱动在同一开机会话中可能无法重新初始化摄像头。
4. 如准备断电，可先运行 `MaixCam Video: Stop RTSP`，然后正常关闭设备供电。
5. 任何真实底盘或机械臂操作结束时，另外执行其L3/L4目标规定的失能、安全位和实体急停检查；本SOP不能代替运动安全流程。

## 4. 排障分流

| 现象 | 先检查 | 处理 |
|---|---|---|
| ESP32无法连接WebREPL | 热点客户列表、当前IPv4、TCP 8266 | 确认设备上电和Wi-Fi；必要时通过USB读取 `WLAN.ifconfig()` |
| WebREPL连接或上传被拒绝 | 是否有另一个WebREPL会话 | 关闭旧会话后重试；不在日志中输出密码 |
| ESP32调试后主程序未运行 | REPL是否中断 `main.py` | 在安全条件下复位，再现场确认原应用状态 |
| MaixCam SSH失败 | 热点、mDNS和当前设备IPv4 | 在设备屏幕确认网络；不把临时IPv4写入Git |
| RTSP启动失败/摄像头忙 | `num`或其它摄像头应用 | 退出占用应用，确保仅有一个摄像头所有者 |
| RTSP日志出现 `No buffer space available` | 是否在同一次开机内停止后重启摄像头 | 停止残留进程并物理重启MaixCam，再退出 `num` |
| 原生RTSP正常，但转发无画面 | FFmpeg和MediaMTX是否同时运行 | 运行 `Stop PC relay`后再 `Start PC relay`；不改为MediaMTX直接拉流 |
| MediaMTX路径 `ready`但字节为0 | FFmpeg publisher状态 | 查看 `logs/mediamtx/ffmpeg-stderr.log`；必须使用 `-c:v copy` 重封装 |
| 本机RTSP/HLS正常，WebRTC页面异常 | 浏览器和WebRTC会话 | 先用 `Probe relay` 确认媒体层，再单独排查浏览器 |

## 5. 问题登记

| 问题 | 状态 | 当前决策 |
|---|---|---|
| ESP32 DHCP地址可变 | 已知约束 | 从手机列表或USB读取，不硬编码 |
| ESP32 WebREPL地址、密码和上传仍为手工 | 待改进 | 保留官方客户端；后续另建安全无线部署目标 |
| WebREPL只允许一个活动连接 | 已知约束 | 连接和上传前关闭旧会话 |
| REPL可中断ESP32底盘 `main.py` | 安全约束 | 调试后复位并现场确认；不把WebREPL用作正式控制协议 |
| MaixCam自启动 `num` 占用摄像头 | 人工步骤 | 每次重启后退出；未经授权不修改自启动 |
| MaixCam摄像头同一会话重启失败 | 未解决 | 避免日常反复启停；发生时物理重启 |
| mDNS可选中不可达IPv6 | 已解决 | RTSP探针和中继包装器显式解析IPv4 |
| MaixCam H.264 mode 0/FU-A与MediaMTX直拉不兼容 | 已解决 | FFmpeg `-c:v copy` 重封装后作为publisher |
| VS Code Remote-SSH不支持设备RISC-V环境 | 已绕开 | 本地VS Code编辑，标准SSH/SCP部署 |
| 视频需顺时针旋转90° | 已确认、未实施 | 在显示与视觉坐标系目标中统一处理 |

## 6. 恢复通道

- ESP32无线失联：使用USB和 `mpremote`读取运行时与网络状态；不默认刷写Flash。
- MaixCam无线失联：使用设备屏幕或USB虚拟网卡恢复SSH。
- MaixCam媒体驱动失败：物理重启，退出 `num`，再按正常顺序启动。
- 设备文件损坏：从Git受控源码或 `device-backups/` 的忽略备份选择性恢复，不覆盖未核实的系统目录。
