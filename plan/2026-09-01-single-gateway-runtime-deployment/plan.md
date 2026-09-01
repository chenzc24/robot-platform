# 冻结MaixCam单网关运行时与部署维护双平面

- 状态：`completed`
- 日期：`2026-09-01`
- 分支：`target/single-gateway-runtime-deployment`
- 最高验证等级：`L0`

## 目标

将用户确认的架构正式写入项目基线：运行时只有电脑与MaixCam必须加入局域网，MaixCam作为电脑唯一设备网关并通过两路UART分别连接ESP32和TCP232/机械臂；部署维护时电脑分别通过ESP32 WebREPL、MaixCam SSH/SCP和机械臂LAN2/DobotStudio更新三端程序。明确统一消息外壳、设备专用命令集、状态反馈、安全职责、启动条件、恢复路径和分阶段实施顺序。

## 工作区初始状态

```text
## target/maixcam-arm-l2...origin/target/maixcam-arm-l2
 M .vscode/settings.json
```

当前事实分支比 `main` 多出机械臂无LAN2运行验证计划与日志；本目标从该分支建立，保留这些事实。`.vscode/settings.json` 是用户已有MicroPython按钮配置，与本目标无关，保持只读、不暂存、不提交。

## 可修改文件

- `AGENTS.md`
- `README.md`
- `docs/overall-plan.md`
- `docs/network/README.md`
- `docs/runtime/README.md`
- `docs/deployment/README.md`
- `plan/2026-09-01-single-gateway-runtime-deployment/plan.md`
- `plan/log.md`

## 只读文件和目录

- `.vscode/settings.json`
- `protocol/`、`src/`、`tests/`、`tools/` 和现有VS Code任务
- `ESP32/`、`Camera/`、`Robot Arm_Claws/`
- 设备文件系统、本地秘密、备份、缓存和临时检查目录

## 共享依赖

- MaixCam RTSP/H.264到电脑视频链路与电脑侧FFmpeg/MediaMTX中继已经通过。
- ESP32历史PS2/CAN底盘链路已经通过，但MaixCam UART到ESP32只存在旧接收骨架，尚未形成正式运动协议。
- MaixCam `/dev/ttyS0` 经TCP232到机械臂LAN1的RPA1双向诊断和固定动作已经通过。
- RPA1工程运行后拔除LAN2仍能完成PING和固定动作；冷启动自动启动工程尚未验证。
- `protocol/runtime-status.schema.json` 是当前服务健康状态契约，不等于未来任务执行状态。

## 预期工作

1. 将总体拓扑改为电脑只向MaixCam下发运行命令，MaixCam分别向ESP32和机械臂分发并汇总状态。
2. 新建运行时基线，定义视频、电脑命令、底盘UART、机械臂UART/TCP232四条通道，以及统一消息外壳、设备命令集、ACK/RUNNING/DONE/FAULT反馈和本地安全边界。
3. 新建部署维护基线，分别记录ESP32 WebREPL/USB、MaixCam SSH/SCP、机械臂LAN2/DobotStudio和TCP232一次性配置；明确部署后启动、健康检查与恢复路径。
4. 更新网络文档，区分开发网络与正式运行网络，明确ESP32 Wi-Fi只承担开发维护而不承载正式运行命令。
5. 同步仓库Agent职责基线，防止后续目标重新采用电脑直控ESP32的旧路线。
6. 给出后续实现顺序：共享协议与模拟器、ESP32串口服务、MaixCam网关、机械臂通用服务、电脑适配器，最后才是真机L2/L3/L4。

## 风险和边界

- 本目标只改变文档中的架构决策，不实现或部署运行代码，不连接、写入、复位或驱动设备。
- MaixCam成为运行时单点网关，但不能成为唯一急停或底层安全控制器。
- 统一消息只统一外壳与状态语义；MaixCam必须解析并转换设备专用命令，禁止透明转发任意运动参数。
- 机械臂断链后的当前动作结果仍可能未知；文档不得声称自动停止或自动完成。
- 机械臂冷启动仍需要人工安全确认、使能和本地启动已配置工程，除非后续另行验证受支持的自动启动方式。

## 验证

- L0：检查两平面拓扑、角色、链路、故障与实施阶段在所有入口文档中一致。
- 检查所有新增链接目标存在。
- 扫描热点、SSH/WebREPL密码、临时DHCP地址和私钥材料。
- `git diff --check`
- `git status --short --branch`

## 实际结果

- 新增 `docs/runtime/README.md`，冻结电脑只与MaixCam通信的运行拓扑、四条通道、统一消息外壳、设备专用命令集、命令生命周期、三端常驻服务、启动顺序和断链行为。
- 新增 `docs/deployment/README.md`，分别定义ESP32 WebREPL/USB、MaixCam SSH/SCP、机械臂LAN2/DobotStudio和TCP232配置入口，明确发布顺序、健康检查和回滚原则。
- 同步 `README.md`、总体方案、网络方案和 `AGENTS.md`，删除电脑通过Wi-Fi正式控制ESP32的旧基线，将ESP32 Wi-Fi收口为开发维护通道。
- 本轮只修改受版本管理的文档，没有连接、写入、复位或驱动真实设备；用户已有 `.vscode/settings.json` 修改保持只读且不进入提交。
- L0检查通过：所有新增本地链接存在，架构关键词交叉扫描未发现旧直控路线，秘密模式扫描未发现凭据；文档内IP仅为已记录的机械臂LAN1/LAN2、TCP232建议值和明确标注的热点网段示例。

## 未解决事项

- 电脑—MaixCam应用连接的具体传输、编码和端口尚未冻结，应在下一共享协议目标中用模拟器和测试向量决定。
- ESP32正式UART底盘服务、MaixCam统一网关、机械臂通用任务服务和电脑客户端均尚未实现或部署。
- 机械臂断链时正在执行动作的结果仍可能为 `UNKNOWN`，不得自动重试非幂等动作。
- 机械臂工程可以在LAN2拔除后继续运行，但冷启动仍需人工确认初始点、使能并通过已配置的本体按键启动，再完成无运动握手。

## 提交意图

```text
docs: split single-gateway runtime and deployment planes
```
