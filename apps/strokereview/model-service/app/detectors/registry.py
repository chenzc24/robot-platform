"""线稿检测器注册表：集中声明内置模型，并允许外部插件替换。"""

from __future__ import annotations

import importlib
import os
from collections.abc import Iterable
from pathlib import Path

from .base import LineArtDetectorAdapter
from .controlnet_aux import ControlNetAuxDetectorAdapter


DEFAULT_MODEL_REPOSITORY = "lllyasviel/Annotators"
BUNDLED_MODEL_DIRECTORY = Path(__file__).resolve().parents[2] / "models"
REQUIRED_MODEL_FILES = (
    "ControlNetHED.pth",
    "table5_pidinet.pth",
    "sk_model.pth",
    "sk_model2.pth",
)


class UnknownDetectorError(ValueError):
    pass


class DetectorRegistry:
    """按稳定 ID 保存检测器；上层无需依赖某个模型的具体 Python 类。"""

    def __init__(self) -> None:
        self._detectors: dict[str, LineArtDetectorAdapter] = {}

    def register(self, detector: LineArtDetectorAdapter, *, replace: bool = False) -> None:
        detector_id = detector.metadata.id
        if not detector_id or not callable(getattr(detector, "predict", None)):
            raise TypeError("A detector must expose metadata.id and predict(image, resolution)")
        if detector_id in self._detectors and not replace:
            raise ValueError(f"Detector '{detector_id}' is already registered")
        self._detectors[detector_id] = detector

    def get(self, detector_id: str) -> LineArtDetectorAdapter:
        try:
            return self._detectors[detector_id]
        except KeyError as exc:
            raise UnknownDetectorError(
                f"Unknown detector '{detector_id}'. Available detectors: {', '.join(self.ids())}"
            ) from exc

    def ids(self) -> list[str]:
        return list(self._detectors)

    def values(self) -> list[LineArtDetectorAdapter]:
        return list(self._detectors.values())


def _builtins(repository: str) -> list[LineArtDetectorAdapter]:
    """注册 controlnet-aux 提供的三个成熟开源线稿/边缘检测器。"""

    return [
        ControlNetAuxDetectorAdapter(
            detector_id="lineart",
            label="Lineart",
            repository=repository,
            class_name="LineartDetector",
            call_parameters={"coarse": False},
        ),
        ControlNetAuxDetectorAdapter(
            detector_id="pidinet",
            label="PiDiNet",
            repository=repository,
            class_name="PidiNetDetector",
            call_parameters={"safe": True, "scribble": False},
        ),
        ControlNetAuxDetectorAdapter(
            detector_id="hed",
            label="HED",
            repository=repository,
            class_name="HEDdetector",
            call_parameters={"safe": True, "scribble": False},
        ),
    ]


def _factory(specification: str):
    module_name, separator, attribute_name = specification.partition(":")
    if not separator or not module_name or not attribute_name:
        raise RuntimeError(
            f"Invalid detector plugin '{specification}'; expected package.module:factory"
        )
    factory = getattr(importlib.import_module(module_name), attribute_name, None)
    if not callable(factory):
        raise RuntimeError(f"Detector plugin factory '{specification}' is not callable")
    return factory


def resolve_model_repository() -> str:
    """Resolve an explicit repository, bundled source weights, or HF fallback."""

    configured = os.getenv("LINEART_MODEL_REPOSITORY")
    if configured:
        return configured
    if BUNDLED_MODEL_DIRECTORY.is_dir() and all(
        (BUNDLED_MODEL_DIRECTORY / filename).is_file()
        for filename in REQUIRED_MODEL_FILES
    ):
        return str(BUNDLED_MODEL_DIRECTORY)
    return DEFAULT_MODEL_REPOSITORY


def build_detector_registry(plugin_specifications: str | None = None) -> DetectorRegistry:
    """构建注册表，并按环境变量加载伙伴提供的自定义检测器插件。

    LINEART_DETECTOR_PLUGINS 格式为 package.module:factory。相同 ID 会替换
    内置适配器，因此无需修改 API、经典后处理或前端即可更换模型。
    """

    repository = resolve_model_repository()
    registry = DetectorRegistry()
    for detector in _builtins(repository):
        registry.register(detector)
    raw = plugin_specifications if plugin_specifications is not None else os.getenv("LINEART_DETECTOR_PLUGINS", "")
    for specification in (item.strip() for item in raw.split(",")):
        if not specification:
            continue
        created = _factory(specification)()
        detectors = created if isinstance(created, Iterable) and not hasattr(created, "metadata") else [created]
        for detector in detectors:
            registry.register(detector, replace=True)
    return registry
