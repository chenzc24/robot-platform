# 图片到线稿坐标（StrokeReview）

源码位于 `apps/strokereview/`，从用户提供的源码包迁入。前端审核、经典图像处理、SVG 输入、本地模型适配器和千问接口保持独立，运行在电脑上。来源及未入库文件见 [IMPORT.md](../../apps/strokereview/IMPORT.md)。

这是绘图任务的上游：图片 → 线稿处理 → 人工审核／编辑 → 正式笔触 JSON。后续由任务编排结合小车定位、确认停止和机械臂坐标转换执行。已删除旧的独立 `app/demo.py`，正式输出只进入 grouped drawing planner；导出动作仍未绑定设备运动，设备职责和通信协议保持原状。

## 启动

需要 Python 3.12/3.13、uv、Node.js 和 npm。首次启动安装锁文件中的依赖。在仓库根目录执行：

```powershell
.\stroke-review.cmd -SkipModels
```

打开 `http://127.0.0.1:5173/`，API 为 `http://127.0.0.1:8000/`。经典 OpenCV 和 SVG 模式无需云端密钥或模型下载。上传图片、调整参数、审核笔触，再导出正式 JSON 与审核 JSON。首次依赖安装需要网络，之后经典模式可以离线运行。

本地 Lineart / PiDiNet / HED 模式使用 Python 3.12 的独立模型环境：

```powershell
.\stroke-review.cmd
```

模型服务优先使用完整的本地权重，否则从模型仓库按需获取。权重和依赖缓存不进入 Git；本机迁移时保留的 ZIP 权重位于忽略的 `apps/strokereview/model-service/models/`。如需使用这些本地权重，可先设置：

```powershell
$env:LINEART_MODEL_REPOSITORY = (Resolve-Path .\apps\strokereview\model-service\models).Path
.\stroke-review.cmd
```

其他电脑需要自行准备权重，或允许首次下载。云端模式及语义审核按原项目文档配置服务端环境变量；真实密钥不得写入源码。开发启动脚本使用进程环境变量，`.env.example` 是配置参考，不代表会自动加载 `.env`。

默认端口与机器人控制台 8080 分离。多工作树同时运行时显式换端口：

```powershell
.\stroke-review.cmd -SkipModels -BackendPort 8100 -FrontendPort 5273 -ModelPort 8110 -ExistingAction Fail
```

关闭本工作树的服务：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\apps\strokereview\stop-dev.ps1
```

启动和停止脚本按项目绝对路径识别进程；不应停止其他工作树或仅因端口相同而终止其他程序。

## 稳定数据接口

- `GET /api/v1/capabilities`：查询处理模式。
- `POST /api/v1/process`：multipart 上传 `file`，`parameters` 为 JSON 字符串。
- `GET /api/v1/schema/strokes.json`：正式坐标 schema。
- 响应中的 `strokes_document` 是服务自动审核后保留的正式笔触，`audit_document` 包含候选、原因和诊断。网页人工编辑之后应使用网页最终导出的 JSON，而非原始 HTTP 响应。

保留 `version`、`coordinate_space`、`canvas`、笔触 `id`、`order`、`points` 和 `closed`。按 `order` 使用笔触，保持每条笔触内部点序。画布原点在左上，x 向右，y 向下；归一化按画布最长边统一缩放：

```text
L = max(canvas.target_width_mm, canvas.target_height_mm)
x_mm = u * L
y_mm = v * L
```

非正方形画布的短边归一化尺寸小于 1；不能分别把 u、v 当成各自边长的百分比，否则会拉伸图形。源图在目标画布内等比居中，留白已经包含在点坐标中。毫米坐标仍是纸面二维坐标，不是机器人基坐标、关节角或相机坐标。机器人侧的纸面标定、笔尖偏移、工作区验证、分段任务与定位接口需要后续独立集成和验证，不能把 JSON 存在视为可执行运动许可。

独立 HTTP 客户端（在仓库根目录运行）：

```powershell
uv run --project apps/strokereview/backend python apps/strokereview/examples/client/process_image.py path/to/image.png --provider classic --output-dir apps/strokereview/stroke-output
```

会生成 `strokes.json`、`audit.json` 和完整响应。自定义端口时增加 `--base-url http://127.0.0.1:8100`。

机器人侧统一入口也可以直接接收图片，并调用同一个本机 API：

```powershell
python app/run_drawing.py path/to/image.png --mode localized_baseline
```

它从 `drawing.local.json` 读取实体画布宽高并强制传入 StrokeReview，随后
把正式笔触、审核文档、完整响应和输入哈希保存在忽略的
`dataset/generated/`。默认只做预演且不连接设备。若要让自动审核结果进入
真实运动，除任务哈希和现场安全门禁外还必须显式提供
`--confirm-auto-review`；也可以先在网页中人工修改并导出 JSON，再把 JSON
交给同一入口。

## 本地验证

```powershell
Push-Location apps/strokereview/backend
uv run --locked pytest -q
Pop-Location
Push-Location apps/strokereview/frontend
npm.cmd ci
npm.cmd test
npm.cmd run build
Pop-Location
```

模型测试和桌面打包说明见 [上游 README](../../apps/strokereview/README.md)。前端构建产物、导出结果、运行状态、环境、模型权重和真实配置均保留在本地。此次验收限定 L0/L1，不包含真实设备连接、云端调用或机器人全流程执行。
