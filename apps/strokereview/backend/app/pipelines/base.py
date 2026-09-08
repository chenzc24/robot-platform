"""完整“文件 -> 笔触”算法管线的公共接口。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from ..models import ProcessingParameters, ProcessResponse


InputKind = Literal["raster", "svg"]


@dataclass(frozen=True)
class PipelineRequest:
    """传给任意完整算法管线的稳定输入，避免实现直接依赖 FastAPI。"""

    content: bytes
    filename: str
    content_type: str | None
    input_kind: InputKind
    parameters: ProcessingParameters


@dataclass(frozen=True)
class PipelineMetadata:
    """管线能力说明；前端算法下拉框也由这些元数据生成。"""

    id: str
    label: str
    description: str
    implementation: str
    input_kinds: frozenset[InputKind] = frozenset({"raster"})
    selectable: bool = True
    requires_model_service: bool = False
    is_cloud: bool = False
    usage_notice: str | None = None


class ImageToStrokesPipeline(Protocol):
    """可替换边界：上传文件和参数 -> 统一 ProcessResponse。

    伙伴若要整体替换“图片到笔触”算法，只需实现此协议并注册，无需改前端。
    """

    metadata: PipelineMetadata

    async def process(self, request: PipelineRequest) -> ProcessResponse:
        ...
