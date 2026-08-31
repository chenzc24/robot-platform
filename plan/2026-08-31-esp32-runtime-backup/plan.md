# ESP32 MicroPython运行时识别与备份

- 状态：`completed`
- 负责人：Agent执行，用户现场配合
- 最高验证等级：`L2`

## 目标

通过COM7连接正常启动的MicroPython运行时，读取版本和文件树，并在不修改设备的前提下将现有文件系统备份到本地忽略目录。

## 工作区初始状态

```text
## main...origin/main
```

上一目标已确认COM7为ESP32-S3。用户已按RST使设备回到正常启动模式，并要求继续；现场仍保持不会意外运动的安全状态。

## 可修改文件

- `.vscode/tasks.json`
- `docs/esp32/development.md`
- `plan/2026-08-31-esp32-runtime-backup/plan.md`
- `plan/log.md`
- `device-backups/`（本地忽略目录，不提交）

## 只读文件和目录

- 其余全部仓库文件
- ESP32设备文件系统和Flash

## 共享依赖

- COM7上的ESP32-S3。
- `.venv` 中的 `mpremote 1.29.0`。
- `.gitignore` 已排除 `device-backups/`。

## 风险和安全门

- 风险：`mpremote`动作会停止当前程序并对MicroPython执行软复位；串口握手也可能触发硬件复位。
- 设备：COM7上的ESP32-S3。
- 用户操作：用户已按RST并要求继续，现场安全状态沿用本轮确认。
- 备份和恢复：本目标只读设备，并将文件复制到时间戳本地目录。
- 运动确认：不上传或执行运动代码；设备已处于用户确认的安全状态。

## 预期工作

1. 读取MicroPython实现、版本、平台和唯一ID摘要。
2. 读取设备文件树，识别现有 `boot.py`、`main.py` 和应用模块。
3. 创建时间戳备份目录并复制设备文件系统。
4. 校验本地备份可读，记录结果；不上传或删除设备文件。
5. 修正联调中发现的 `mpremote fs tree` 参数兼容问题。

## 验证

- `mpremote connect COM7 exec <只读运行时信息>`
- `mpremote connect COM7 fs tree -vsh :`
- 对本地备份执行文件数量、大小和SHA-256清单检查。
- `git check-ignore device-backups`
- `git diff --check`
- `git status --short --branch`

## 实际结果

- `mpremote`通过COM7成功连接MicroPython 1.27.0（2026-05-11），构建目标为 `ESP32_GENERIC_S3-SPIRAM_OCT`，平台为ESP32。
- 文件树读取成功：设备根目录有11个Python文件，`SmartHybridChasisDemo/` 中另有相同的11个文件。
- 已将全部22个文件、125684字节复制到本地忽略目录 `device-backups/esp32/20260831-111429/`。
- 根目录和子目录的11对同名文件逐一计算SHA-256，全部一致；备份文件均可读取。
- 根目录 `boot.py` 不初始化外设；根目录 `main.py` 会初始化UART、CAN和电机。当前 `robot_config.py` 为 `RUN_MODE="ps2"`，启动后进入PS2控制循环。
- 第一次文件树命令使用了互斥的 `-s` 与 `-h` 参数而失败，已将VS Code任务修正为兼容mpremote 1.29.0的 `-vh` 并验证通过。
- 本目标没有上传、删除或修改设备文件，未执行底盘运动。

## 未解决事项

- 当前程序在复位后会重新初始化CAN和电机，下一次复位前仍需维持现场安全状态。
- 尚未配置手机热点、`webrepl_setup`和无线连接。
- 设备根目录与 `SmartHybridChasisDemo/` 的重复文件后续应在代码迁移目标中确定保留策略，本目标不删除设备文件。

## 经验信号（供人工审阅）


## 提交意图

```text
docs: record ESP32 MicroPython runtime backup
```
