# 验证机械臂无LAN2运行路径

- 状态：`completed`
- 日期：`2026-09-01`
- 最高验证等级：`L3`
- 提交意图：测试完成后仅提交本目标计划和事实日志

## 目标

区分并验证两个问题：机械臂冷启动后既有TCP工程是否已经运行，以及工程经LAN2启动后，拔除LAN2是否仍能由MaixCam经UART/TCP232和机械臂LAN1持续完成诊断与受控动作。

## 工作区初始状态

- 当前分支：`target/maixcam-arm-l2`
- 工作区已有用户修改：`.vscode/settings.json`
- 该修改与本目标无关，不检查内容、不修改、不暂存。

## 文件所有权

可修改：

- `plan/2026-09-01-arm-no-lan2-autostart-test/plan.md`
- `plan/log.md`
- `tmp/legacy_arm_once.py`（忽略的单次测试工具）
- `tmp/run_guarded_legacy_once.sh`（忽略的UART保护入口）

只读：

- `src/maixcam/arm/`
- `Camera/code/used/通讯案例-机械臂/`
- `protocol/arm-diagnostic-v1.md`
- `docs/robot-arm/lan1-diagnostic.md`
- MaixCam现有部署目录、机械臂现有工程和TCP232配置

保护范围：

- 不修改机械臂IP、TCP232模式/参数、示教点、速度参数或安全配置。
- 不上传或替换ESP32、MaixCam或机械臂产品程序；只允许向MaixCam `/tmp` 上传本轮单次测试工具，结束后删除。
- 不连接LAN2，不启动DobotStudio。

## 预期工作

1. 只读确认MaixCam SSH、`/dev/ttyS0`所有者和现有受保护UART入口。
2. 由用户确认L3现场安全门、LAN2未连接和单次固定P2预期动作。
3. 因机械臂初始已在P2，先单次发送`Initialize`到P1并等待用户确认，再单次发送`biao00300031-020`返回P2；每一步读取旧程序`yunxing`响应。
4. 禁止自动重试；异常、超时或结果未知时停止并由现场人员确认实际状态。
5. 恢复MaixCam原UART所有者，记录实际动作、响应和无LAN2路径结论。

## 风险和停止条件

- 旧程序将`biao`后的坐标只用于解析，实际固定执行`MovJ(P2, {"user": 0, "v": 100})`。
- `yunxing`在动作前返回，只代表请求被接受，不代表动作完成。
- 发送前必须确认人员现场、实体急停可用、周边净空、底盘固定、机械臂安全位、全局低速和负载。
- 方向、速度、范围异常、重复动作、通信超时或现场观察不一致时立即实体急停并停止软件操作。

## 验证

- L0：`git diff --check`、计划差异和秘密检查。
- L2：MaixCam SSH、UART所有者、无LAN2和TCP232物理状态由现场与只读检查共同确认。
- L3：只发送一次固定旧协议消息；用户现场观察P2动作并确认最终状态。
- 不执行底盘动作；`Initialize`与`biao`分两次人工授权执行，任一步均不自动重试。

## 实际结果

- 更正：用户所说“P2已经达到”描述的是测试前机械臂所在位置，不是本轮测试结果；此前Agent未发送任何运动命令，不能据此判定验证通过。
- 用户随后再次授权立即执行，并维持现场急停、净空、底盘固定、安全位、低速和负载等准备条件。
- 首次在LAN2未连接时，Agent通过受保护UART入口精确发送一次旧协议`Initialize`。MaixCam成功写出完整消息，但2秒内没有收到`yunxing`，用户确认机械臂完全没有动作；没有重发，也没有继续发送`biao`。
- 后续确认机械臂实际运行的是本仓库RPA1诊断工程，旧协议`Initialize`不属于该工程协议，因此旧协议超时本身不能证明LAN2是运行期必需链路。
- 用户重新连接LAN2并启动RPA1后，MaixCam发送无运动`PING`成功，往返326毫秒，机械臂返回`ready`。
- 用户拔除LAN2并等待10秒后，MaixCam再次发送无运动`PING`成功，往返194毫秒；返回`ready`、`motion_enabled=false`和`fixed_step_consumed=false`。
- 沿用本轮明确的L3现场安全授权，Agent只发送一次RPA1固定`STEP`：J1正向1°、等待1秒、反向1°回位，速度和加速度5%，无自动重试。机械臂返回成功，往返3201毫秒，最终`ready`、`motion_enabled=false`和`fixed_step_consumed=true`；用户现场确认动作正常。
- 因此已验证：RPA1工程一旦运行，拔除LAN2不会中断`MaixCam /dev/ttyS0 → TCP232 → 机械臂LAN1`运行链路；LAN2不承载运行期控制数据。
- 测试退出后`/dev/ttyS0`已恢复由launcher持有；MaixCam `/tmp`和本地`tmp/`中的旧协议单次探针均已删除。
- ESP32和底盘未参与；没有修改机械臂IP、TCP232参数、安全配置、示教点、产品程序或机械臂工程。

## 结论和剩余风险

- 已通过：RPA1已启动时，LAN2可以拔除；MaixCam经LAN1完成了双向状态通信和一次受控真实动作。
- 未通过/未验证：机械臂冷启动和实体使能是否会自动启动RPA1。当前事实仍表明“实体使能”不能替代“确认工程正在运行”。
- 机械臂每次重新上电后，在配置并验证可靠的开机任务或本地启动入口前，仍应通过LAN2/DobotStudio启动RPA1并先用无运动`PING`确认`ready`；确认后即可拔除LAN2。
- 旧协议`Initialize`/`biao`与RPA1诊断协议不是同一运行契约，不能混用；本目标没有验证旧工程的任意坐标控制或完成反馈。
- 本轮固定STEP只证明既定的单次低速动作链路，不代表通用动作接口、断链恢复、幂等语义或上电自启动已经完成。
