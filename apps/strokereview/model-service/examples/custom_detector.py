"""Working detector plugin example, intentionally not registered by default.

Set LINEART_DETECTOR_PLUGINS=examples.custom_detector:create_detector to load it.
Change metadata.id to "lineart", "pidinet" or "hed" to replace a built-in
detector without changing the main backend or frontend.
"""

from PIL import Image, ImageFilter, ImageOps

from app.detectors import DetectorMetadata


class PartnerEdgeDetector:
    metadata = DetectorMetadata(
        id="partner_edge",
        label="伙伴边缘模型示例",
        repository="local-plugin",
        implementation="examples.custom_detector.PartnerEdgeDetector",
    )

    @property
    def loaded(self) -> bool:
        return True

    def predict(self, image: Image.Image, resolution: int) -> Image.Image:
        resized = ImageOps.contain(image.convert("RGB"), (resolution, resolution))
        return ImageOps.invert(resized.convert("L").filter(ImageFilter.FIND_EDGES))


def create_detector() -> PartnerEdgeDetector:
    return PartnerEdgeDetector()
