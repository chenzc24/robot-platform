# MaixCam开发通道配置

- 状态：`completed`
- 负责人：Agent执行，用户负责设备屏幕和必要的物理操作
- 最高验证等级：`L2`

## 目标

在不产生底盘或机械臂运动的前提下，将MaixCam Pro接入现有2.4 GHz开发热点，确认设备身份、系统与MaixPy版本，建立电脑和VS Code可复用的SSH/SFTP开发通道，并在任何写入前备份设备当前应用与相关配置。MaixVision仅保留为发现、预览和恢复工具，不作为唯一代码源。

## 工作区初始状态

```text
## main...origin/main
 M .vscode/settings.json
```

`.vscode/settings.json` 中存在未提交的MicroPython按钮配置，归属不明且可能是用户当前编辑；本目标将其视为只读用户修改，不覆盖、不暂存、不提交。其余工作区干净。

## 可修改范围

- `plan/2026-08-31-maixcam-development-channel/plan.md`
- `plan/log.md`
- `docs/maixcam/`
- `src/maixcam/`
- `tests/maixcam/`
- `.vscode/tasks.json`（仅在不依赖或覆盖现有设置修改的情况下）
- Git忽略的 `device-backups/maixcam/` 与MaixCam本机配置文件
- `C:/Users/90590/.ssh/id_ed25519_robot_maixcam`、对应公钥和 `C:/Users/90590/.ssh/config` 中独立的 `robot-maixcam` 主机段
- MaixCam设备：仅限Wi-Fi、SSH公钥、开发目录和无运动诊断；写入前必须先读取并备份

## 只读范围

- `.vscode/settings.json` 的用户未提交修改
- `Camera/` 原始资料、固件镜像、安装包和案例源码
- `ESP32/`、`Robot Arm_Claws/`、`src/esp32/` 与真实ESP32
- 机械臂、TCP232和底盘运动硬件
- MaixCam系统固件、分区和驱动；本目标不烧录镜像、不升级系统

## 共享依赖与已知事实

- MaixCam Pro是视觉与机械臂唯一运行网关；它通过独立UART连接ESP32，并通过另一UART和TCP232连接机械臂LAN1。
- 原始课件给出的UART波特率为115200，但本目标不接线或发送业务命令。
- 官方文档支持同局域网Wi-Fi或USB虚拟网卡连接；SSH/SFTP端口为22，设备名和IP可在“设置→设备信息”查看。
- 热点、SSH密码和私钥不得进入Git、日志或设备备份清单输出。

## 实施步骤

1. 由用户在MaixCam屏幕确认设备型号、启动正常和当前设备信息。
2. 将MaixCam连接到现有2.4 GHz热点，记录本地IP/设备名但不提交真实凭据。
3. 从电脑验证ICMP或邻居发现、TCP 22和SSH主机身份；只读采集系统、MaixPy、存储和运行进程信息。
4. 在任何设备写入前，备份当前可变配置与用户应用到Git忽略目录，并记录文件清单和校验值。
5. 建立独立SSH密钥或其它可恢复的VS Code Remote-SSH通道；不在仓库保存密码或私钥。
6. 建立本地 `src/maixcam/` 最小入口和无运动探针，通过SFTP部署到独立开发目录，验证运行日志和文件回读。
7. 编写配置、恢复和日常使用文档；不启动相机以外的串口控制，不触发底盘或机械臂动作。

## 用户需要协助

- 给MaixCam供电并确认屏幕进入功能选择界面。
- 在设备“设置→WiFi”中选择现有热点并完成连接。
- 告知“设置→设备信息”显示的设备名和IP；如需要，确认SSH首次登录或在屏幕上处理授权提示。
- 本目标不需要连接机械臂、TCP232或ESP32串口，也不需要运动安全门确认。

## 验证

- L0：文档、JSON/Python语法、秘密扫描、`git diff --check`。
- L1：本地MaixCam无硬件代码或部署脚本测试（如本目标新增）。
- L2：设备发现、TCP 22、SSH只读命令、SFTP备份/校验、独立目录最小无运动程序运行与日志回读。
- 完成时运行 `git status --short --branch`，只暂存目标范围，记录未执行项和剩余风险。

## 恢复路径

- SSH或Wi-Fi失败时使用设备屏幕重新配置网络。
- 无线链路不可用时使用USB虚拟网卡配合MaixVision或SSH恢复。
- 写入仅限独立开发目录和SSH授权；删除新增内容即可恢复，系统镜像不变。
- 本地备份和原始固件镜像保留在Git忽略目录与只读资料库中。

## 实际结果

- 设备通过mDNS发现为 `maixcam-6c7d.local`，当前IPv4为动态地址；ICMP、TCP 22和OpenSSH握手通过。
- 只读确认Buildroot 2023.11.2、Linux 5.10.4、`riscv64`、Python 3.11.6和MaixPy API 4.12.5；设备约29 GB存储，使用约5%。
- 配置前完整备份 `/root`、`/maixapp` 和 `/boot` 到Git忽略目录，远端与本地文件数分别为70、775、27且完全一致，并生成872文件SHA-256清单。
- 生成项目专用Ed25519密钥，设备原先没有 `/root/.ssh`；安装单一公钥后通过BatchMode验证免密登录。用户SSH配置新增 `robot-maixcam` 别名，使用mDNS而非动态IP。
- 核对官方要求后确认VS Code Remote-SSH不支持riscv64且设备资源不足，因此采用“VS Code本地编辑 + OpenSSH/SCP任务”的架构，没有安装VS Code Server或第三方MaixCode扩展。
- 新增无 `maix` 导入的探针、2项本地测试和5个VS Code任务；探针上传前后SHA-256一致，并在设备返回预期JSON身份快照。
- 验证期间设备曾短暂退出热点，电脑侧mDNS和旧DHCP地址均不可达；用户重新连接后，`maixcam-6c7d.local` 再次解析到设备，专用密钥登录、SCP上传、SHA-256校验和探针运行全部恢复。该结果验证了应用文件与SSH授权未因普通网络掉线丢失，但热点连接本身仍不是安全或实时链路。
- MaixVision 1.2.2已启动；因用户同时操作该窗口，自动UI控制停止，设备连接和实时画面预览留作人工确认。

## 未解决事项

- MaixVision设备连接和实时画面尚未形成验证结果。
- 本目标没有改变默认系统密码；虽然已使用专用密钥，出厂密码仍是开发热点上的剩余风险，应在用户确认恢复方式后单独更改。
- 尚未迁移视觉应用、相机预览、ESP32 UART或机械臂UART网关。
- `import maix` 会初始化默认UART0通信协议；后续视觉服务必须显式处理该占用并在接线前完成端口所有权设计。
- 第三方MaixCode扩展尚未完成源码与权限审计，因此未安装。

## 提交意图

```text
feat: establish MaixCam VS Code development channel
```
