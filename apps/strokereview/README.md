# 线稿预处理与笔触审核工具

> 已迁入 Robot Platform：仓库入口、运行方式与机器人侧接口边界见 [迁移接入文档](../../docs/console/strokereview.md)。以下保留上游应用说明，其中机器人执行设想不代表本仓库已实现或验证的运动流程。

这是移动机械臂绘图项目的数据预处理前端。它可以在本机把 PNG/JPG/SVG 转成与机器人无关的二维连续笔触，并分别导出正式几何文件 `strokes.json` 和完整审计文件 `audit.json`。

## 当前能做什么

- PNG/JPG 清晰线稿：OpenCV 灰度、CLAHE、降噪、Otsu 二值化、形态学，scikit-image 小物体/小孔洞清理，OpenCV Zhang–Suen 骨架化。
- 骨架转笔触：Skan 提取骨架分支，先迭代剪除可恢复毛刺，再用物理尺度 PCA 切线和 NetworkX 最大权重匹配保持主干连续；笔径内的小断口可安全连接，之后由 OpenCV/SciPy 简化和平滑。
- 普通照片：可选 Lineart、PiDiNet 或 HED，本机 CPU 推理；模型输出会继续进入同一套骨架和笔触流程。
- 云端 API 模式：调用阿里云百炼 `qwen-image-edit-plus-2025-12-15` 把插画或照片生成黑白线稿，再进入同一套本地骨架、笔触和审核流程；缓存命中不会重复调用云端。
- 可选语义审核：`qwen3.8-max-0902` 理解原图主体、姿态和关系，按稳定候选 ID 评价删除每笔造成的辨识损失，并检查渐进绘制结果；模型不生成或修改坐标，失败会回退到本地评分。
- SVG：保留 `path`、`line`、`polyline`、`polygon`、`circle`、`ellipse`、`rect` 的矢量路径；展开嵌套 transform；自适应采样直线、Bezier 和圆弧；保留闭合属性和基本元素顺序。
- 网页预览：原图、二值线稿、单像素骨架和结构化笔触四种视图。
- 人工编辑：所有笔触均可保留、待确认或删除；选中笔触后可在任意位置拆成前后两条；也可按住鼠标或触控笔直接补画新笔触。删除、拆分和新增都会同步到两种导出文件。
- 确定性导出：同一输入和参数得到相同 ID、笔触顺序和坐标。
- 最小线上保护：可选 HTTP Basic Auth，必须放在 HTTPS 后使用。

`strokes.json` 只包含下游需要的 canvas 和 `keep` 几何；每条笔触的 `order` 是“整体轮廓和主要结构优先”的重要性绘制序号。由于机械臂每笔都从固定原点出发并返回，系统不再按笔间距离做 TSP 排序，也不反转路径。网页会显示候选编号、重要性排名和正式绘制顺序。全部参数、评分、原因、`keep/uncertain/discard` 状态及警告保存在 `audit.json`。

## 开发、接手与替换模型

完整的项目目录说明、两层可替换接口、插件示例、运行/模型要求，以及每个网页参数对应的真实代码公式见：

- [项目架构与模型替换指南](项目架构与模型替换指南.md)
- [下游接入与调用说明](下游接入与调用.md)

生成不含依赖、模型权重、缓存、密钥和构建产物的源码交付包：

```powershell
powershell -ExecutionPolicy Bypass -File .\package-source.ps1
```

主后端现在通过 `ImageToStrokesPipeline` 注册表调用完整的“输入 → 笔触”流程；模型服务通过 `LineArtDetectorAdapter` 注册表调用 Lineart/PiDiNet/HED。外部实现可用环境变量注册或覆盖，不需要修改 FastAPI 路由、审核界面或导出契约；新增完整 pipeline 也会自动出现在网页算法下拉框。

## 一键本地启动

前置条件：Windows PowerShell、`uv`、Node.js LTS 和 npm。不需要 Docker、Git 或 GPU。

```powershell
powershell -ExecutionPolicy Bypass -File .\start-dev.ps1
```

脚本会检查并补齐项目依赖，启动三个隐藏的本地进程，然后自动打开网页。启动成功后命令会返回，PowerShell 窗口可以继续使用或直接关闭；关闭窗口不会停止服务。

- 网页：http://127.0.0.1:5173
- 主 API：http://127.0.0.1:8000
- API 文档：http://127.0.0.1:8000/docs
- CPU 模型服务：http://127.0.0.1:8010/api/health
- 日志：`.devlogs/`

启动前脚本会检查三个端口是否被残留进程占用。任一服务提前退出或启动超时时，终端会直接显示服务名称、退出码、对应错误日志路径及日志末尾，不再只给出通用报错。

正常退出请运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\stop-dev.ps1
```

安全重启请运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\restart-dev.ps1
```

重复执行 `start-dev.ps1` 时，如果三个服务都健康，脚本会直接复用现有服务并打开网页；如果本项目的服务缺失或不健康，脚本会安全重启。不会结束其他项目的 Node 或 Python 进程。

如果需要让启动脚本留在前台持续监控，并在按 `Ctrl+C` 时停止三个服务，可增加 `-Wait`：

```powershell
powershell -ExecutionPolicy Bypass -File .\start-dev.ps1 -Wait
```

后端默认不启用 Uvicorn 热重载，以避免 OpenCV/SciPy 等模块变更时重载进程异常退出。修改 Python 后请运行 `restart-dev.ps1`。确实需要边开发边自动重载时，可显式使用：

```powershell
powershell -ExecutionPolicy Bypass -File .\start-dev.ps1 -ReloadBackend
```

只用经典算法、不启动模型服务：

```powershell
powershell -ExecutionPolicy Bypass -File .\start-dev.ps1 -SkipModels
```

只验证三项服务能启动并立即停止：

```powershell
powershell -ExecutionPolicy Bypass -File .\start-dev.ps1 -NoBrowser -SmokeTest
```

首次选择 Lineart、PiDiNet 或 HED 时会从 Hugging Face 下载对应权重，之后复用本机缓存。默认缓存位于用户目录下的 `.cache\huggingface\hub`，不写入本项目文件夹。三种模型都强制使用 CPU，首次加载和处理通常比经典算法慢。

## 网页使用方法

1. 拖入或选择 PNG、JPG 或 SVG。
2. 选择算法。扫描稿或黑白线稿优先用“经典 OpenCV”；插画优先试 Lineart；普通照片优先试 PiDiNet；HED 作为另一种边缘风格；需要更强的语义线稿效果时选择“API 模式（千问云端线稿）”。
3. 调整细节、清理、平滑和物理尺寸参数。
   栅格模式还可设置自动最大笔数，并选择是否让千问参与语义重要性审核；人工恢复和补画不受最大笔数限制。
4. 点击“开始处理”或“重新处理”。滑块变化本身不会请求后端。
5. 对照二值、骨架和笔触预览。
6. 点击任意彩色笔触，在审核区选择“保留”“待确认”或“删除”。删除后线条立即隐藏；打开“显示已删除笔触”可点选灰色虚线并恢复。
7. 批量处理待确认笔触：点击“批量选择待确认笔触”，逐条点选橙色线条（再次点击可取消），或点击“全选待确认”；随后可将整组选中笔触一起保留、设为待确认或删除。
8. 拆分笔触：选中一条笔触，点击“拆分笔触”，再直接点击线条上希望断开的位置。拆出的两条笔触可继续独立编辑和再次拆分。
9. 人工添加：点击“人工添加笔触”，在笔触画布中按住鼠标或触控笔拖动；松开后创建一条默认保留的 `manual` 笔触。可连续绘制，完成后点击“结束添加”。
10. 正向选择：点击“全不选并开始正选”，所有候选会变为可见的“待确认”；逐条点击需要的线即可保留。点击“暂存并编辑”后可补画、拆分或修改笔触，再点“继续正向选择”会保留进度接着选；“完成并保存选择”提交当前会话，“恢复开始前状态”撤销整次会话。也可点击“只选极简外轮廓”：插画、照片、HED 与千问 API 模式会同时检查线条法向两侧的原图颜色，两侧近色的内部墨线不会入选；经典线稿/扫描稿模式只按几何外边界判断。
11. 除 `strokes.json` 外，可点击“导出逐笔 Python ZIP”：每条正式 `keep` 笔触按最终顺序生成独立的 `stroke_0001.py`、`stroke_0002.py` 等文件，文件内提供 `points` Python 列表，并统一打包为 `strokes_python.zip`。
12. 下载正式 `strokes.json`，并同时保存 `audit.json` 供追溯。

如果本地模型服务不可用，主后端不会让整次任务失败，而会退回经典算法，并在 `audit.json` 写入 `local_model_fallback` 警告。

### 千问 API 模式

API 模式只在后端读取密钥。开始前在 Windows 用户环境变量、部署平台 Secret 或未提交的 `.env` 中配置：

```text
DASHSCOPE_API_KEY=<百炼 API Key>
QWEN_DASHSCOPE_BASE_URL=https://<业务空间ID>.cn-beijing.maas.aliyuncs.com/api/v1
QWEN_IMAGE_MODEL=qwen-image-edit-plus-2025-12-15
QWEN_VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_VISION_MODEL=qwen3.8-max-0902
```

重新启动后端后，网页会在算法列表中启用“API 模式”。如果配置缺失，该选项仍会显示但不可选择，并给出缺失项；密钥不会进入 capabilities、处理响应、日志或前端构建。

默认风控配置如下，可通过同名环境变量覆盖：

- 每日最多发起 20 次未缓存云请求（`QWEN_DAILY_REQUEST_LIMIT`）。
- 同时最多 1 个云请求（`QWEN_MAX_CONCURRENCY`）。
- 超时 600 秒（`QWEN_CLOUD_TIMEOUT_SECONDS`）。
- 本地缓存开启（`QWEN_CACHE_ENABLED=true`）；Windows 默认写到 `%LOCALAPPDATA%\StrokeReview\qwen-cache`，Docker 使用独立持久卷。
- 输出图片最大 20 MB（`QWEN_MAX_OUTPUT_MB`）。
- 语义审核默认每日最多 100 次、并发 1；分别由 `QWEN_VISION_DAILY_REQUEST_LIMIT` 和 `QWEN_VISION_MAX_CONCURRENCY` 控制。语义结果单独缓存。

前端每次提交 API 模式前都会确认图片将上传到阿里云并可能计费。云端失败会明确返回错误，不会静默改用经典或本地模型；这样用户不会误以为拿到的是千问结果。成功结果的模型、输出 SHA-256 和缓存命中状态会写入 `audit.json` warnings，但不会记录下载签名 URL。固定 seed 只能提高相对稳定性，不能让生成式模型严格确定；云端输出哈希会参与 processing/stroke 身份，避免不同生成结果冒用同一个 ID。

## 分别运行和测试

主后端使用项目自己的 Python 3.13 环境：

```powershell
cd backend
uv sync --group dev
uv run pytest -q
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

在模型服务已运行时，可验证“主 API → 本地 Lineart → 骨架 → 笔触”整条链路：

```powershell
cd backend
uv run python scripts/smoke_local_model.py
```

模型服务固定使用 uv 管理的 Python 3.12，避免深度学习依赖与主后端冲突：

```powershell
cd model-service
uv sync --python 3.12 --group dev
uv run uvicorn app.main:app --host 127.0.0.1 --port 8010
```

前端：

```powershell
cd frontend
npm.cmd install
npm.cmd test
npm.cmd run build
npm.cmd run dev
```

## 架构与开源组件

| 步骤 | 组件 | 用途与选择理由 | 许可证/维护情况 | 降级方案 |
| --- | --- | --- | --- | --- |
| 栅格预处理 | OpenCV contrib | 成熟的阈值、形态学、轮廓与 `ximgproc.thinning` | Apache-2.0；活跃、官方文档完整 | scikit-image skeletonize |
| 小物体/孔洞清理 | scikit-image | 经过验证的形态学操作 | BSD-3-Clause；活跃、文档完整 | OpenCV 连通域 |
| 骨架分支 | Skan | 直接提取骨架路径、端点和分叉 | BSD-3-Clause；0.13.x、有文档 | 自建 NetworkX 像素图 |
| 分叉组合 | NetworkX | 稳定的图、匹配和遍历能力 | BSD-3-Clause；活跃、文档完整 | 确定性贪心配对 |
| 简化/平滑 | OpenCV + SciPy | Douglas–Peucker 与 B 样条实现成熟 | Apache-2.0 / BSD-3-Clause | 仅导出原折线 |
| SVG | svgelements + defusedxml | 成熟解析 path、圆弧、transform，并安全解析 XML | MIT / PSF；有文档 | 明确报错，不做不完整手写解析 |
| 照片转线稿 | controlnet-aux | 一个适配层提供 Lineart、PiDiNet、HED，CPU 可运行 | 代码 Apache-2.0；有 PyPI/GitHub 文档 | 自动回退经典算法 |

本项目自行实现的部分集中在：组件编排、物理尺度参数、分支方向配对代价、干扰评分、确定性排序/ID、审核契约和网页交互。没有重复实现阈值、骨架、图匹配、样条或完整 SVG 语法。

### 模型权重说明

`controlnet-aux` 代码为 Apache-2.0。默认使用 `lllyasviel/Annotators` 仓库的 Lineart、PiDiNet、HED 权重；该权重仓库在 Hugging Face 标为 `other`，未给出足够清晰的商业授权。当前配置适合用户指定的非商业本地实验，不应据此推断可商用。若以后商业化，应先完成权重来源和授权审核，或替换为许可明确的模型。

完整 Windows 桌面包使用不带 `-SkipModels` 的 `build-desktop.ps1` 构建，会同时打包 CPU 模型服务及 Lineart、PiDiNet、HED 权重，安装到 `model-service/models`，运行时优先读取这些本地文件。因此接收方无需安装 Python，也无需在第一次使用本地模型时联网。包含 PyTorch 后发行包体积会显著增加；`-SkipModels` 仅适用于只需要经典、SVG 和云端模式的轻量包。

`package-source.ps1` 生成的完整源码包也包含同样的 `model-service/models` 权重目录。下游开发者仍需按锁文件安装 Python/Node 依赖，但模型权重无需另行下载；若显式设置 `LINEART_MODEL_REPOSITORY`，则以该设置为准。

## 参数和数据格式

- `detail_level`：0–100；影响处理分辨率、SVG 采样精度和折线简化。
- `cleanup_strength`：0–100；影响小对象阈值和强清理时的形态学闭运算。
- `minimum_length_mm`：映射到目标物理尺寸后的最小笔触长度。
- `smoothing`：0–100；控制 B 样条平滑误差。
- `target_width_mm` / `target_height_mm`：最终物理画布宽高；作品保持原比例并居中适配。旧 API 请求省略高度时仍按作品比例推导高度。
- `effective_resolution_mm`：目前参与 classic 小对象清理和 SVG 采样容差。
- `pen_width_mm`：实际笔头直径；用于真实笔宽预览，并把长距离、同方向且落在一个笔径内的冗余平行笔触安全降为可恢复的 `uncertain`。
- `max_strokes`：1–5000，只限制算法自动保留结果；超限候选进入可恢复的 `uncertain`。
- `ai_semantic_review`：是否调用视觉模型理解内容并审核候选笔触。`ai_review_quality` 控制审核候选规模，`max_cloud_review_calls` 限制单次任务的视觉审核调用次数。
- `provider_parameters`：外部 pipeline 自定义 JSON 参数，内置算法不使用。

JSON Schema 可从运行中的主 API 获取：

- `/api/v1/schema/strokes.json`
- `/api/v1/schema/audit.json`

坐标空间按物理画布最长边归一化，原点左上，x 向右、y 向下；因此画布较短边可能小于 1，作品在画布中的留白也会体现在坐标中。正式文件不包含算法分数或被排除的线条。

## 最小访问保护

线上部署同时设置：

```text
APP_ACCESS_USERNAME=reviewer
APP_ACCESS_PASSWORD=<足够长的随机密码>
```

设置后，除 `/api/health` 外的网页和 API 都要求 HTTP Basic Auth。两个变量必须一起设置。Basic Auth 本身不加密传输，必须由云平台或反向代理提供 HTTPS。生产环境还应补充上传限流、实例网络隔离、持久日志和更完整的账户权限系统。默认上传上限为 25 MB，可用 `MAX_UPLOAD_MB` 调整。

## Docker 与线上部署

仓库包含主应用的多阶段 `Dockerfile`、模型服务的 `model-service/Dockerfile` 和 `compose.yaml`。模型权重使用命名卷缓存：

```bash
docker compose up --build
```

预期网页地址为 `http://localhost:8080`。模型容器只在 compose 内网提供服务，不暴露公网端口。

**本机没有 Docker，因此截至 2026-08-31 未进行 Docker 构建或容器运行验证。容器必须由 CI 或云平台远程构建验收。** 模型镜像包含 CPU 版 PyTorch，体积会明显大于主应用镜像；首次运行仍需下载权重，生产环境应配置持久缓存和外网访问。

## 已知限制

- SVG 的文字、滤镜、裁剪路径不会转成笔触，只写入结构化警告；嵌入位图尚未转入栅格流程，外部图片不会联网读取。
- 视觉模型的笔触审核依赖彩色编号图；候选特别密集或超过当前强度的审核上限时，剩余笔触使用本地物理/拓扑评分，并在摘要中标为部分审核。
- 当前工作目录和 Docker 镜像默认不内置模型权重，首次使用需联网下载；`package-source.ps1` 生成的完整源码包和完整 Windows 桌面发行包都包含离线权重。
- Dockerfile 尚未在本机验证。

替换整条算法时实现 `ImageToStrokesPipeline`；只替换照片线稿模型时实现 `LineArtDetectorAdapter`。保持 `ProcessResponse`、`StrokesDocument` 和 `AuditDocument` 不变，前端不需要理解具体算法内部实现。
