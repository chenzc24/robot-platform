"""完整图片到笔触管线的注册、选择和插件加载逻辑。"""

from __future__ import annotations

import importlib
import os
from collections.abc import Iterable

from .base import ImageToStrokesPipeline, PipelineRequest
from .builtins import builtin_pipelines


class UnknownPipelineError(ValueError):
    pass


class PipelineRegistry:
    """按 provider ID 隔离算法实现，使 API 和前端不依赖具体模型类。"""

    def __init__(self) -> None:
        self._pipelines: dict[str, ImageToStrokesPipeline] = {}

    def register(self, pipeline: ImageToStrokesPipeline, *, replace: bool = False) -> None:
        metadata = pipeline.metadata
        if not metadata.id or not callable(getattr(pipeline, "process", None)):
            raise TypeError("A pipeline must expose metadata.id and async process(request)")
        if metadata.id in self._pipelines and not replace:
            raise ValueError(f"Pipeline '{metadata.id}' is already registered")
        self._pipelines[metadata.id] = pipeline

    def get(self, pipeline_id: str) -> ImageToStrokesPipeline:
        try:
            return self._pipelines[pipeline_id]
        except KeyError as exc:
            raise UnknownPipelineError(
                f"Unknown provider '{pipeline_id}'. Available providers: {', '.join(self.selectable_ids())}"
            ) from exc

    def selectable_ids(self) -> list[str]:
        return [
            pipeline_id
            for pipeline_id, pipeline in self._pipelines.items()
            if pipeline.metadata.selectable
        ]

    def selectable_pipelines(self) -> list[ImageToStrokesPipeline]:
        return [self._pipelines[pipeline_id] for pipeline_id in self.selectable_ids()]

    async def process(self, request: PipelineRequest):
        """根据用户选择和输入类型找到管线并执行。

        SVG（除显式 mock 外）始终走 SVG 管线，避免先栅格化而丢失矢量语义。
        """

        pipeline_id = request.parameters.provider
        if request.input_kind == "svg" and pipeline_id != "mock":
            pipeline_id = "svg"
        pipeline = self.get(pipeline_id)
        if request.input_kind not in pipeline.metadata.input_kinds:
            raise UnknownPipelineError(
                f"Provider '{pipeline_id}' does not accept {request.input_kind} input"
            )
        return await pipeline.process(request)


def _load_factory(specification: str):
    module_name, separator, attribute_name = specification.partition(":")
    if not separator or not module_name or not attribute_name:
        raise RuntimeError(
            f"Invalid pipeline plugin '{specification}'; expected package.module:factory"
        )
    module = importlib.import_module(module_name)
    factory = getattr(module, attribute_name, None)
    if not callable(factory):
        raise RuntimeError(f"Pipeline plugin factory '{specification}' is not callable")
    return factory


def load_external_pipelines(registry: PipelineRegistry, specifications: str | None = None) -> None:
    """从 STROKE_PIPELINE_PLUGINS 加载伙伴实现，并允许同 ID 覆盖内置算法。"""

    raw = specifications if specifications is not None else os.getenv("STROKE_PIPELINE_PLUGINS", "")
    for specification in (item.strip() for item in raw.split(",")):
        if not specification:
            continue
        created = _load_factory(specification)()
        pipelines = created if isinstance(created, Iterable) and not hasattr(created, "metadata") else [created]
        for pipeline in pipelines:
            registry.register(pipeline, replace=True)


def build_pipeline_registry(plugin_specifications: str | None = None) -> PipelineRegistry:
    """先注册内置算法，再加载外部插件；API 启动时调用一次。"""

    registry = PipelineRegistry()
    for pipeline in builtin_pipelines():
        registry.register(pipeline)
    load_external_pipelines(registry, plugin_specifications)
    return registry
