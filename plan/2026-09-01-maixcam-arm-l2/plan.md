# 打通MaixCam到机械臂LAN1链路并执行一次受控运动

- 状态：`completed`
- 负责人：Agent实施，用户现场监护并操作实体急停
- 最高验证等级：`L3`

## 目标

按冻结架构建立 `MaixCam UART → PCB TCP232 → 机械臂LAN1` 的双向诊断闭环。先使用带版本、序列号、CRC和超时的 `PING/PONG` 代替旧裸字符串，再在用户明确授权的L3安全门下执行一次固定、低速、可回位的J1小幅动作。运动请求不携带角度、速度或示教点，机械臂项目每次启动最多接受一次。

## 工作区初始状态

```text
## main...origin/main
 M .vscode/settings.json
```

从同步的 `main` 创建 `target/maixcam-arm-l2`。`.vscode/settings.json` 是用户已有修改，本目标保持只读，不覆盖、不暂存、不提交。开始检查时MaixCam SSH和ESP32 WebREPL在线；MaixCam RTSP与本机视频中继未运行，与本目标无关，不自动启动。

## 可修改文件

- `protocol/`
- `src/maixcam/arm/`
- `src/robot_arm/diagnostics/`
- `tests/protocol/`、`tests/maixcam/`、`tests/robot_arm/`
- `tools/maixcam/`
- `.vscode/tasks.json`
- `README.md`
- `docs/overall-plan.md`
- `docs/network/README.md`
- `docs/maixcam/`、`docs/robot-arm/`
- `plan/2026-09-01-maixcam-arm-l2/plan.md`
- `plan/log.md`

## 只读文件和目录

- `.vscode/settings.json`
- `ESP32/`、`Camera/`、`Robot Arm_Claws/`
- `src/esp32/` 和ESP32设备文件系统
- MaixCam现有视频程序及摄像头资源
- 机械臂旧项目、示教点、IP、安全参数和既有运动配置
- 本地秘密、SSH配置、设备备份和真实地址覆盖

## 共享依赖

- 架构基线：MaixCam是机械臂唯一运行网关；机械臂LAN1由MaixCam经UART/TCP232控制，LAN2仅用于维护和部署。
- 旧相机资料使用 `/dev/ttyS0`、115200波特率访问机械臂路径；真机检查时必须确认该设备节点未被launcher或其他进程占用。
- TCP232基线为115200 8N1、TCP Client、目标机械臂 `192.168.5.1:5200`；不在未导出当前配置前修改。
- 机械臂旧示例收到 `Initialize` 或 `biao...` 会调用 `MovJ`，本目标禁止发送这些字符串并必须停止该项目。
- `protocol/runtime-status.schema.json` 的结构化状态和错误码原则。

## 风险和安全门

- L2阶段机械臂诊断项目只接受 `PING` 并返回 `PONG`；该阶段已完成且机械臂无运动。
- L3只增加固定 `STEP`：J1正向1°、等待1秒、J1反向1°回到原位；速度和加速度均为5%，平滑过渡关闭。请求不得携带运动参数，机械臂项目每次启动最多执行一次，MaixCam不自动重试。
- 连接或启动前用户必须确认人员在现场、实体急停可操作、机械臂未使能且旧运动项目已停止。若本体可能因自动运行旧项目产生动作，则停止并升级为L3目标。
- MaixCam写入前读取目标目录和串口占用，备份被替换的项目文件；部署到独立目录，不覆盖视频或视觉项目。
- 不改变机械臂IP、TCP232工作模式/参数或安全配置；如果现值与基线不一致，停止并请求用户确认。
- 诊断失败只报告断开、占用、CRC、序列号或超时，不发送探测性旧指令，不自动重试运动，不重启机械臂。动作中出现异常由现场人员立即操作实体急停；若第一段动作后失败，不自动发送补偿动作。
- 恢复路径：停止MaixCam独立诊断进程并恢复launcher；机械臂诊断项目停止后保留原项目不变；MaixCam备份用于恢复被占用串口前状态。

## 预期工作

1. 定义双端可实现的ASCII诊断帧、CRC、序列号、最大长度、超时和错误语义。
2. 实现MaixCam可注入UART网关和独立L2探针，显式检查串口所有权并硬拒绝运动类命令。
3. 实现机械臂LAN1无运动回显项目，并静态证明不包含运动API或示教点。
4. 增加跨端向量、分片/粘包、CRC、超时、错误响应、串口占用和运动拒绝测试及VS Code任务。
5. L1通过后只读检查MaixCam `/dev/ttyS0`、相关进程和TCP232/机械臂维护状态。
6. 用户通过LAN2启动机械臂诊断项目后，部署MaixCam诊断目录并执行一次 `PING/PONG`、一次断链超时和恢复验证。
7. 用户于2026-09-01明确确认现场急停可用、周围无人无障碍、底盘已固定、机械臂处于安全位且负载已确认，并授权执行上述固定动作。扩展协议、双端实现和测试后，部署并仅下发一次 `STEP`。

## 验证

- L0：VS Code JSON、文档、配置模板、正式源码ASCII和秘密扫描。
- L1：协议、MaixCam网关、资源所有权、机械臂诊断解析器和安全源码测试；全部既有回归。
- L2：MaixCam UART双向 `PING/PONG`、匹配序列号和往返时间；真机已通过，往返约163ms，全程机械臂无运动。
- L3：用户现场监护下仅执行一次固定J1动作；确认正向1°、停1秒、反向1°回位，随后停止项目并失能。任何异常立即实体急停；未收到完成响应不得自动重试。
- `git diff --check`
- `git status --short --branch`

## 实际结果

- 建立 `RPA1` ASCII帧、CRC-16/CCITT-FALSE、序列号、96字节上限、分片/粘包恢复、超时和稳定错误码；L2只接受 `PING/PONG`。
- MaixCam端形成POSIX UART传输、一次在途请求网关、L2/L3独立探针及launcher守护脚本。守护脚本验证supervisor和UART所有者身份，临时释放 `/dev/ttyS0`，退出时恢复launcher。
- DobotStudio Pro 4.6机械臂端形成独立 `main.py`。L3扩展只接受无参数 `STEP`，硬编码J1正向1°、等待1秒、反向1°回位，速度和加速度5%、`cp=0`；每次项目运行最多消费一次，失败或响应丢失不重试。
- L2真机 `PING/PONG` 成功，序列号1，往返163毫秒，机械臂无动作。
- 用户完成L3安全确认后执行两次彼此独立的人工授权验证。第一次返回 `DONE`、往返3525毫秒，但用户未观察；系统拒绝直接重发。用户停止并重新运行机械臂项目、重新授权后，第二次返回 `DONE`、往返3221毫秒，用户确认链路打通。
- 两次L3探针退出后launcher supervisor均保持运行；最终 `/dev/ttyS0` 所有者为 `/maixapp/apps/launcher/launcher`。未修改机械臂IP、TCP232参数、安全参数、示教点、底盘或视频服务。
- L0/L1最终验证通过：协议10项、ESP32 30项、MaixCam 40项、机械臂7项、开发工具23项，共110项；31个Python源文件检查、52个VS Code任务、JSON、Bash语法、工作区校验和 `git diff --check` 通过。

## 未解决事项

- 未通过物理拔线执行真机断链超时测试；本地网关超时与错误路径测试已通过。后续若验证真机断链，必须单独建立目标并把动作结果标记为未知，禁止自动重试。
- 本目标只验证固定一次动作，不是通用机械臂业务协议。任意轨迹、状态查询、队列、取消、恢复和控制台集成需另建目标。
- MaixCam视频在本目标开始时未运行，与机械臂链路无关；本目标未启动或修改视频服务。

## 提交意图

```text
feat: validate maixcam arm lan1 link
```
