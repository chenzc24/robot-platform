"""Physical canvas fitting shared by raster, SVG, mock and partner pipelines."""

from __future__ import annotations

from dataclasses import dataclass

from .models import CanvasSpec, ProcessingParameters


@dataclass(frozen=True)
class FittedCanvasLayout:
    canvas: CanvasSpec
    millimeters_per_source_unit: float
    millimeters_per_normalized_unit: float
    offset_x_mm: float
    offset_y_mm: float

    def normalize_source_point(self, x: float, y: float) -> tuple[float, float]:
        return (
            (self.offset_x_mm + x * self.millimeters_per_source_unit)
            / self.millimeters_per_normalized_unit,
            (self.offset_y_mm + y * self.millimeters_per_source_unit)
            / self.millimeters_per_normalized_unit,
        )


def fit_canvas_layout(
    coordinate_width: float,
    coordinate_height: float,
    parameters: ProcessingParameters,
    *,
    source_width: int | None = None,
    source_height: int | None = None,
) -> FittedCanvasLayout:
    """Fit source coordinates into the requested physical canvas without stretching.

    ``target_height_mm=None`` preserves the legacy behavior where the artwork
    width determines the physical height. New web requests send both page
    dimensions and therefore receive centered contain-fitting with margins.
    """

    if coordinate_width <= 0 or coordinate_height <= 0:
        raise ValueError("Canvas source dimensions must be positive")
    target_width_mm = float(parameters.target_width_mm)
    target_height_mm = (
        float(parameters.target_height_mm)
        if parameters.target_height_mm is not None
        else round(target_width_mm * coordinate_height / coordinate_width, 4)
    )
    scale = min(
        target_width_mm / coordinate_width,
        target_height_mm / coordinate_height,
    )
    content_width_mm = coordinate_width * scale
    content_height_mm = coordinate_height * scale
    offset_x_mm = (target_width_mm - content_width_mm) / 2
    offset_y_mm = (target_height_mm - content_height_mm) / 2
    normalization_mm = max(target_width_mm, target_height_mm)
    metadata_width = source_width or max(1, round(coordinate_width))
    metadata_height = source_height or max(1, round(coordinate_height))
    canvas = CanvasSpec(
        width=round(target_width_mm / normalization_mm, 6),
        height=round(target_height_mm / normalization_mm, 6),
        source_width=metadata_width,
        source_height=metadata_height,
        source_aspect_ratio=round(metadata_width / metadata_height, 6),
        target_width_mm=target_width_mm,
        target_height_mm=target_height_mm,
    )
    return FittedCanvasLayout(
        canvas=canvas,
        millimeters_per_source_unit=scale,
        millimeters_per_normalized_unit=normalization_mm,
        offset_x_mm=offset_x_mm,
        offset_y_mm=offset_y_mm,
    )
