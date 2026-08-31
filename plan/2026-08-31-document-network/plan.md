# 整理网络方案文档

- 状态：`completed`
- 负责人：Agent实施，用户确认方案
- 最高验证等级：`L0`

## 目标

将已经确认的电脑、ESP32、MaixCam、TCP232和机械臂网络方案独立写入 `docs/network/`，形成后续配置与联调的唯一详细网络基线。

## 工作区初始状态

```text
## main...origin/main
```

工作区干净。

## 可修改文件

- `docs/network/README.md`
- `docs/overall-plan.md`
- `plan/2026-08-31-document-network/plan.md`
- `plan/log.md`

## 只读文件和目录

- `AGENTS.md`
- `ESP32/`
- `Camera/`
- `Robot Arm_Claws/`
- 其他未列入可修改范围的文件

## 共享依赖

- `docs/overall-plan.md` 已冻结的设备职责和网络决策。
- 机械臂LAN1默认地址 `192.168.5.1`、运行端口 `5200`、LAN2固定地址 `192.168.200.1`。
- 开发期使用2.4 GHz手机热点的既定决策。

## 风险和安全门

- 风险：文档中的地址或控制边界如果表达错误，会误导后续配置。
- 设备：不需要。
- 用户操作：不需要。
- 备份和恢复：由Git记录文档历史。
- 运动确认：不适用。

## 预期工作

1. 新建 `docs/network/README.md`，记录拓扑、职责、地址、发现、数据路径、安全、故障降级和验收步骤。
2. 在总体方案网络章节添加详细文档入口，避免两份文档互相冲突。
3. 更新维护日志并完成L0检查。

## 验证

- `git diff --check`
- `git status --short --branch`
- 使用 `rg` 检查热点、LAN1、LAN2、TCP232、Tailscale、WebREPL和安全链路边界。
- 检查文档相对链接有效。

## 实际结果

- 已建立 `docs/network/README.md`，覆盖物理拓扑、节点职责、热点动态地址、LAN1/LAN2地址、TCP232建议配置、控制路径、Tailscale边界、断链降级、接入步骤和验收清单。
- 已在总体方案网络章节加入详细网络文档入口。
- `git diff --check` 通过。
- `rg` 确认热点、LAN1、LAN2、TCP232、Tailscale、WebREPL和安全边界均有明确说明。
- 相对链接目标存在；未连接、写入或驱动真实设备。

## 未解决事项

- TCP232实际地址、串口参数和目标端口仍需在设备接入时通过配置页面或导出文件确认。
- 机械臂通信中断时对正在执行动作的本体行为仍需L2/L3专项验证。

## 经验信号（供人工审阅）


## 提交意图

```text
docs: document robot network architecture
```
