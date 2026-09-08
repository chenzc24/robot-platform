"""把开源 controlnet-aux 检测器包装成项目统一接口。"""

from __future__ import annotations

import threading
from typing import Any

from PIL import Image

from .base import DetectorMetadata


class ControlNetAuxDetectorAdapter:
    """Lineart、PiDiNet、HED 共用的延迟加载适配器。

    该类不实现模型算法，只调用 controlnet_aux 中经过封装的开源实现；
    class_name 和 call_parameters 由注册表配置，因此三种模型共用一套代码。
    """

    def __init__(
        self,
        *,
        detector_id: str,
        label: str,
        repository: str,
        class_name: str,
        call_parameters: dict[str, Any],
    ) -> None:
        self.metadata = DetectorMetadata(
            id=detector_id,
            label=label,
            repository=repository,
            implementation=f"controlnet_aux.{class_name}",
        )
        self._class_name = class_name
        self._call_parameters = call_parameters
        self._model: object | None = None
        self._load_lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _load(self):
        """第一次实际推理时才下载/加载权重，并用锁避免并发重复加载。"""

        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            try:
                import controlnet_aux

                detector_class = getattr(controlnet_aux, self._class_name)
                # controlnet-aux/Hugging Face 负责权重缓存；默认仓库由注册表传入。
                self._model = detector_class.from_pretrained(self.metadata.repository)
            except Exception as exc:
                raise RuntimeError(
                    f"Could not load {self.metadata.id} from {self.metadata.repository}: {exc}"
                ) from exc
        return self._model

    def predict(self, image: Image.Image, resolution: int) -> Image.Image:
        """执行检测并把各种可能的返回类型统一成 Pillow 灰度图。"""

        detector = self._load()
        output = detector(
            image,
            detect_resolution=resolution,
            image_resolution=resolution,
            output_type="pil",
            **self._call_parameters,
        )
        if not isinstance(output, Image.Image):
            output = Image.fromarray(output)
        return output.convert("L")
