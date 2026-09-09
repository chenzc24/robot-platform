"""Physical contain-fit and configured content margin tests."""

import pytest

from app.canvas_layout import fit_canvas_layout
from app.models import ProcessingParameters


def test_margin_preserves_full_canvas_metadata_and_insets_content():
    parameters = ProcessingParameters(
        target_width_mm=700,
        target_height_mm=200,
        content_margin_mm=10,
    )
    layout = fit_canvas_layout(700, 200, parameters)
    assert layout.canvas.target_width_mm == 700
    assert layout.canvas.target_height_mm == 200
    assert layout.offset_x_mm == pytest.approx(35)
    assert layout.offset_y_mm == pytest.approx(10)
    assert layout.normalize_source_point(0, 0) == pytest.approx((35 / 700, 10 / 700))
    assert layout.normalize_source_point(700, 200) == pytest.approx((665 / 700, 190 / 700))


def test_margin_cannot_consume_short_edge():
    parameters = ProcessingParameters(
        target_width_mm=700,
        target_height_mm=200,
        content_margin_mm=100,
    )
    with pytest.raises(ValueError, match="no drawable"):
        fit_canvas_layout(700, 200, parameters)
