"""项目自带的图片/SVG 转笔触管线及其界面说明。"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool

from ..classic_provider import process_classic
from ..local_model_provider import process_local_model
from ..mock_provider import process_mock
from ..qwen_cloud_provider import process_qwen_cloud, qwen_cloud_availability
from ..svg_provider import process_svg
from ..vision_review_provider import review_process_result
from .base import ImageToStrokesPipeline, PipelineMetadata, PipelineRequest


class ClassicPipeline:
    """清晰线稿和扫描稿使用的纯经典、确定性处理管线。"""

    metadata = PipelineMetadata(
        id="classic",
        label="经典 OpenCV（线稿/扫描稿）",
        description="OpenCV + scikit-image + Skan + NetworkX + SciPy 的本地确定性流程",
        implementation="app.pipelines.builtins.ClassicPipeline",
    )

    async def process(self, request: PipelineRequest):
        # OpenCV/Skan/SciPy are CPU-bound synchronous libraries. Running them
        # directly in an async FastAPI route blocks health checks and makes the
        # whole website appear frozen until processing finishes.
        result = await run_in_threadpool(
            process_classic,
            request.content,
            request.filename,
            request.parameters,
        )
        if not request.parameters.ai_semantic_review:
            return result
        return await review_process_result(
            request.content,
            request.filename,
            result,
        )


class LocalDetectorPipeline:
    """先调用可选深度线稿模型，再复用经典骨架到笔触处理。"""

    def __init__(self, provider_id: str, label: str, description: str) -> None:
        self.metadata = PipelineMetadata(
            id=provider_id,
            label=label,
            description=description,
            implementation="app.pipelines.builtins.LocalDetectorPipeline",
            requires_model_service=True,
        )

    async def process(self, request: PipelineRequest):
        result = await process_local_model(
            request.content,
            request.filename,
            request.content_type,
            request.parameters,
        )
        if not request.parameters.ai_semantic_review:
            return result
        return await review_process_result(
            request.content,
            request.filename,
            result,
        )


class QwenCloudPipeline:
    """调用千问图像编辑生成线稿，再复用本地骨架到笔触流程。"""

    metadata = PipelineMetadata(
        id="qwen_cloud",
        label="API 模式（千问云端线稿）",
        description="阿里云百炼千问生成黑白线稿后，复用本地经典骨架与笔触流程",
        implementation="app.pipelines.builtins.QwenCloudPipeline",
        is_cloud=True,
        usage_notice="图片会上传至阿里云百炼；未命中缓存的成功生成可能消耗免费额度或产生费用。",
    )

    @staticmethod
    def availability() -> tuple[bool, str | None]:
        return qwen_cloud_availability()

    async def process(self, request: PipelineRequest):
        return await process_qwen_cloud(
            request.content,
            request.filename,
            request.content_type,
            request.parameters,
        )


class MockPipeline:
    """仅用于诊断前后端闭环；它不会分析上传图片内容。"""

    metadata = PipelineMetadata(
        id="mock",
        label="Mock（诊断）",
        description="固定的确定性测试笔触，不分析图片内容",
        implementation="app.pipelines.builtins.MockPipeline",
        input_kinds=frozenset({"raster", "svg"}),
    )

    async def process(self, request: PipelineRequest):
        return await run_in_threadpool(
            process_mock,
            request.content,
            request.filename,
            request.content_type,
            request.parameters,
        )


class SvgPipeline:
    """SVG 专用管线；注册表会自动把 SVG 请求路由到这里。"""

    metadata = PipelineMetadata(
        id="svg",
        label="SVG 矢量路径",
        description="保留 SVG 路径语义并采样为统一笔触",
        implementation="app.pipelines.builtins.SvgPipeline",
        input_kinds=frozenset({"svg"}),
        selectable=False,
    )

    async def process(self, request: PipelineRequest):
        return await run_in_threadpool(
            process_svg,
            request.content,
            request.filename,
            request.parameters,
        )


def builtin_pipelines() -> list[ImageToStrokesPipeline]:
    """集中列出网页可选算法；顺序同时决定前端下拉框顺序。"""

    return [
        ClassicPipeline(),
        LocalDetectorPipeline("lineart", "Lineart（插画，CPU）", "controlnet-aux Lineart 线稿提取后复用经典骨架流程"),
        LocalDetectorPipeline("pidinet", "PiDiNet（照片，CPU）", "controlnet-aux PiDiNet 边缘提取后复用经典骨架流程"),
        LocalDetectorPipeline("hed", "HED（备用，CPU）", "controlnet-aux HED 边缘提取后复用经典骨架流程"),
        QwenCloudPipeline(),
        MockPipeline(),
        SvgPipeline(),
    ]
