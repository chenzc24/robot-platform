"""可替换线稿检测器必须遵守的最小接口。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from PIL import Image


@dataclass(frozen=True)
class DetectorMetadata:
    """用于界面、审计和排错的检测器说明，不参与模型推理。"""

    id: str
    label: str
    repository: str
    implementation: str


class LineArtDetectorAdapter(Protocol):
    """可替换边界：RGB 图片 -> 灰度线稿置信图。

    新模型只需实现这里的 metadata、loaded 和 predict，无需了解骨架、
    笔触评分或导出格式。predict 返回 Pillow 灰度图，后端会统一后处理。
    """

    metadata: DetectorMetadata

    @property
    def loaded(self) -> bool:
        ...

    def predict(self, image: Image.Image, resolution: int) -> Image.Image:
        ...
