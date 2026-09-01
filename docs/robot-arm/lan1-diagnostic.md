# MaixCam到机械臂LAN1链路验证

## 链路

```text
MaixCam /dev/ttyS0 (115200 8N1)
    ↔ PCB TCP232（TCP Client）
    ↔ 机械臂 LAN1 192.168.5.1:5200（TCP Server）
```

机械臂项目位于 `src/robot_arm/diagnostics/`，实现
`protocol/arm-diagnostic-v1.md` 的 `PING/PONG` 和一次性固定 `STEP/DONE`。
`point.json` 为空，不使用初始化、使能、点动、轨迹、示教点或夹爪API。

`STEP` 仅用于L3链路验收：J1正向1°、等待1秒、反向1°回位，速度和加速度
均为5%，平滑过渡关闭。请求不含角度、速度或示教点参数；机械臂项目每次启动
最多消费一次，MaixCam不自动重试。这不是通用机械臂运动协议。

## L2无运动验证

1. 人员留在现场并能操作实体急停；机械臂周边没有人员或障碍物。
2. 通过LAN2连接DobotStudio，停止旧相机通信项目。旧项目收到 `Initialize` 或
   `biao...` 会执行运动，不能作为连通性探针。
3. 在DobotStudio项目的 `main.py` 中使用
   `src/robot_arm/diagnostics/main.py`，确认 `point.json` 为 `[]`，启动诊断程序。
   程序阻塞在 `TCPRead` 且不抛异常表示正在等待TCP232输入，不是卡死。
4. 确认TCP232为115200 8N1、TCP Client，目标为机械臂LAN1的
   `192.168.5.1:5200`。如果现值不同，只记录并停止，不擅自修改。
5. MaixCam侧确认 `/dev/ttyS0` 无其他进程占用后，运行独立L2探针一次。探针
   使用Linux POSIX串口接口，不导入会自动启动Maix通信协议的 `maix` 包。
6. 只以CRC正确且序列号匹配的 `PONG` 作为通过；任何超时或错误均停止测试。

通过只证明双向数据链路成立，不授权机械臂运动。

## L3固定动作验证

1. 明确本轮动作、停止条件和失败处理，并由现场人员确认实体急停可用、周围
   无人无障碍、底盘固定、机械臂处于安全位、低速且负载已确认。
2. 保持上述 `main.py` 运行并停在 `TCPRead`；机械臂按本体要求使能。
3. 部署 `src/maixcam/arm/` 后，通过受保护入口执行一次：

   ```sh
   /root/robot-platform/arm/run_guarded_l3.sh EXECUTE_FIXED_J1_STEP
   ```

4. 现场观察J1小幅偏转、停顿约1秒并回位；机器响应必须为匹配序列号的
   `DONE`。异常立即使用实体急停，不能依赖Wi-Fi或软件急停。
5. 探针退出后确认 `/dev/ttyS0` 重新由
   `/maixapp/apps/launcher/launcher` 持有；停止DobotStudio项目并失能机械臂。

若操作者漏看动作，不得直接重发。当前机械臂项目会返回
`motion_already_consumed`；必须人工停止并重新运行 `main.py`、重新检查安全条件、
重新授权后才能再次执行。若命令超时或响应丢失，实际动作状态视为未知，不重试。

## 已验证事实（2026-09-01）

- L2 `PING/PONG` 成功，序列号1，往返163毫秒。
- L3固定动作在两次独立人工授权、两次独立机械臂项目运行中均返回 `DONE`；
  往返分别为3525毫秒和3221毫秒。第二次由用户现场观察并确认链路打通。
- 每次运行后Maix launcher supervisor保持运行，`/dev/ttyS0` 所有者恢复为
  launcher；未修改机械臂IP、TCP232参数、安全参数或示教点。

## 常见阻塞

| 现象 | 原因或判断 | 处理 |
|---|---|---|
| DobotStudio停在 `TCPRead` | 正常阻塞等待 | 保持运行，等待MaixCam请求 |
| `uart_owner_not_launcher` | 串口被未知进程占用 | 不强杀，查明所有者后再继续 |
| launcher被停止后出现僵尸PID | 文件描述符可能已经释放 | 以 `fuser /dev/ttyS0` 为准，不只看 `kill -0` |
| `motion_already_consumed` | 本次机械臂项目已执行过STEP | 停止并重新运行项目，重新走安全门 |
| STEP超时或响应丢失 | 动作结果未知 | 禁止重试，先从现场和本体状态确认 |
| PowerShell远端命令中的 `$变量` 被本机展开 | SSH备份路径或复制目标异常 | 远端脚本用单引号包裹，或避免在一行命令中混用本机和远端变量 |
