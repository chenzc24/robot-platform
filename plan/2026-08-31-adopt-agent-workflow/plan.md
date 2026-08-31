# 引入机器人项目工作流内核

- 状态：`completed`
- 负责人：Agent实施，用户决策
- 最高验证等级：`L0`

## 目标

将 `agent-workflow-kernel` 的计划—实施—验证—日志—提交闭环引入本仓库，并针对ESP32、MaixCam、机械臂和真实运动安全进行精简定制。

## 工作区初始状态

执行 `git status --short --branch` 的结果为：

```text
## main...origin/main
```

工作区干净，可以开始本目标。

## 可修改文件

- `AGENTS.md`
- `README.md`
- `plan/README.md`
- `plan/target-plan.template.md`
- `plan/log.md`
- `plan/2026-08-31-adopt-agent-workflow/plan.md`

## 只读文件和目录

- `docs/overall-plan.md`
- `ESP32/`
- `Camera/`
- `Robot Arm_Claws/`
- `tmp/`

后三个设备资料目录和临时分析目录均由 `.gitignore` 排除，本目标不得修改其中内容。

## 共享依赖

- `docs/overall-plan.md` 中已经冻结的设备职责、网络拓扑和安全原则。
- `.gitignore` 中对资料、秘密配置和设备备份的保护。
- 上游 `chenzc24/agent-workflow-kernel` 的计划—日志—经验分层。

## 预期工作

1. 创建项目专用 `AGENTS.md`，保留上游内核的范围、所有权、验证和提交纪律。
2. 增加机器人硬件安全门、协议联动规则、秘密信息保护及分级验证要求。
3. 加入精简的目标计划说明、模板和维护日志。
4. 更新仓库README，说明开发目标的执行方法。
5. 暂不加入经验库；经验提炼仅在用户明确要求时启用。

## 验证

- `git diff --check`
- `git status --short --branch`
- 使用 `rg` 检查计划、日志、验证等级、资料只读和真实运动确认规则。
- 使用 `git check-ignore` 复核三个资料目录仍未进入版本管理。
- 审阅暂存差异，确认只包含本计划声明的文件。

这些检查覆盖本目标全部文档行为和仓库保护规则；本目标不改动运行代码，因此不需要设备测试或完整测试套件。

## 实际结果

- 已建立机器人项目专用 `AGENTS.md`，并保留上游内核的目标范围、文件所有权、风险验证、事实日志和提交闭环。
- 已增加资料只读保护、秘密信息保护、设备写入恢复要求以及L3/L4真实运动人工安全门。
- 已建立目标计划说明、模板和维护日志；经验目录按决策暂不启用。
- `git diff --check` 通过。
- `rg` 检查确认计划、日志、L0–L4、三个资料目录、真实运动确认和经验触发规则均存在。
- `git check-ignore` 确认 `ESP32/`、`Camera/`、`Robot Arm_Claws/` 和 `tmp/` 仍被忽略。
- 未连接、写入或驱动任何真实设备。

## 未解决事项

- 无。本工作流将在下一目标“VS Code开发环境基线”中首次用于运行代码和开发配置。

## 经验信号（供人工审阅）

本次只是引入工作流基线，暂不提炼经验。

## 提交意图

提交信息：

```text
docs: adopt robot development workflow kernel
```
