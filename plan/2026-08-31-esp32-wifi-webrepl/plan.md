# ESP32手机热点与WebREPL联调

- 状态：`completed`
- 负责人：Agent执行，用户提供热点和现场条件
- 最高验证等级：`L2`

## 目标

通过COM7为当前MicroPython会话连接用户手机2.4 GHz热点，确认ESP32获得局域网地址；随后配置独立WebREPL密码并验证电脑到ESP32的无线REPL连接。未经验证不修改现有启动文件。

## 工作区初始状态

```text
## main...origin/main
```

工作区干净。MicroPython 1.27.0和设备文件系统已完成只读备份；用户已开启热点并明确授权使用本轮提供的热点凭据。热点密码不得写入Git、计划、日志或命令输出。

## 可修改文件

- `.vscode/tasks.json`
- `src/esp32/app/boot.py`
- `src/esp32/app/network_boot.py`
- `src/esp32/app/secrets.example.py`
- `src/esp32/app/secrets.py`（本机忽略文件）
- `src/esp32/README.md`
- `docs/esp32/development.md`
- `plan/2026-08-31-esp32-wifi-webrepl/plan.md`
- `plan/log.md`
- ESP32运行时网络状态
- ESP32根目录 `boot.py`、`network_boot.py` 与 `secrets.py`

## 只读文件和目录

- 其余仓库文件
- ESP32现有底盘应用文件，除非计划在写入前明确更新范围

## 共享依赖

- COM7上的MicroPython 1.27.0。
- 用户手机2.4 GHz热点。
- 官方WebREPL客户端及4至9字符独立密码限制。
- 已完成的本地设备文件系统备份。

## 风险和安全门

- 风险：`mpremote`会停止现有PS2控制程序并软复位；后续复位可能重新初始化CAN和电机。
- 设备：COM7上的ESP32-S3。
- 用户操作：热点已开启；现场继续保持底盘不会意外运动的状态。
- 备份和恢复：写入前已有完整文件备份；本轮先采用非持久运行时连接。
- 运动确认：不发送底盘运动命令。

## 预期工作

1. 通过串口在当前MicroPython会话启用STA并连接手机热点，不打印密码。
2. 读取连接状态和DHCP地址，确认电脑与ESP32处于可达网段。
3. 确定4至9字符WebREPL独立密码，通过串口启用并验证无线终端。
4. 无线验证通过后，将有超时和异常隔离的Wi-Fi与WebREPL引导模块写入启动流程；真实凭据只存在本机忽略文件和设备文件系统。
5. 重启后重新验证DHCP、TCP 8266和只读无线REPL；不改动或发送底盘运动命令。
6. 将Windows下不可用且会回显密码的官方CLI终端任务替换为官方WebREPL浏览器客户端入口。

## 验证

- 读取 `WLAN.isconnected()`、`WLAN.status()` 和 `ifconfig()`。
- 电脑到ESP32执行 `ping` 和TCP 8266连通检查。
- 官方WebREPL协议完成登录并执行只读REPL命令。
- 重启后重复局域网与无线REPL检查。
- `git diff --check`
- `git status --short --branch`

## 实际结果

- ESP32在当前会话中成功连接2.4 GHz手机热点，`WLAN.isconnected()`为真，并通过DHCP取得 `10.114.1.97/24`；电脑切到同一热点后ICMP互访成功。
- 通过串口临时启动WebREPL后，TCP 8266可达；官方WebREPL协议完成鉴权，返回MicroPython 1.27.0，并成功执行不写文件的REPL标记命令。
- 新增 `network_boot.py`，采用20秒有界轮询连接Wi-Fi并启动WebREPL；`boot.py`隔离网络异常，不初始化运动外设。真实凭据只存在Git忽略的本地 `secrets.py` 和设备文件系统。
- 按 `network_boot.py`、`secrets.py`、`boot.py` 的顺序上传到COM7，并在设备端完成三文件语法检查；没有修改设备原有 `main.py` 或其他底盘文件。
- 硬复位后ESP32自动恢复相同DHCP地址和TCP 8266服务，无线鉴权与只读REPL探针再次成功。探针结束后执行最终硬复位，确认ICMP与TCP 8266恢复，不再进入REPL干扰原有PS2启动流程。
- 固定版本的官方CLI完成鉴权后在Windows因缺少 `termios` 退出，并意外在状态行回显密码。VS Code已移除该CLI终端和上传任务，改为打开官方 `webrepl.html` 浏览器客户端。
- 本地Python语法、VS Code任务JSON、官方浏览器客户端存在性、秘密扫描和Git格式检查均通过。
- 本轮只进行L2连接和配置验证，没有发送底盘运动命令，也没有执行L3运动验证。

## 未解决事项

- DHCP地址仍可能变化；mDNS或设备发现工具留待后续网络诊断目标。
- Windows日常无线操作当前使用官方浏览器客户端，命令行多文件同步需等待上游修复或另建目标实现不泄密的薄封装。
- 设备原有底盘 `main.py` 尚未审计迁入受版本管理源码，本轮保留原状。

## 经验信号（供人工审阅）

- 固定版本官方WebREPL CLI在Windows交互REPL和凭据输出方面存在可迁移的安全/兼容性问题；后续部署工具选择应显式验证这两项。

## 提交意图

```text
feat: enable ESP32 Wi-Fi WebREPL bootstrap
```
