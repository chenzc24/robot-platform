from __future__ import annotations

from app.models import ProcessingParameters
from app.svg_provider import process_svg


def svg_parameters(**updates) -> ProcessingParameters:
    values = {"provider": "classic", "target_width_mm": 200, "detail_level": 80}
    values.update(updates)
    return ProcessingParameters(**values)


def test_svg_shapes_paths_and_nested_transforms_are_preserved() -> None:
    content = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">
      <g transform="translate(10 5)">
        <g transform="scale(2)">
          <line id="line" x1="0" y1="0" x2="50" y2="10" stroke="#000" fill="none"/>
        </g>
      </g>
      <circle id="circle" cx="150" cy="50" r="20" stroke="black" fill="none"/>
      <path id="curve" d="M 10,90 C 60,10 140,10 190,90" stroke="black" fill="none"/>
    </svg>'''

    result = process_svg(content, "nested.svg", svg_parameters())
    strokes = result.audit_document.strokes

    assert len(strokes) == 3
    assert strokes[0].source_ref == "line"
    assert strokes[0].source_order == 0
    assert strokes[0].points == [(0.05, 0.025), (0.55, 0.125)]
    assert strokes[1].source_ref == "circle"
    assert strokes[1].closed is True
    assert len(strokes[2].points) > 2
    assert all(
        0 <= coordinate <= 1
        for stroke in strokes
        for point in stroke.points
        for coordinate in point
    )
    assert result.strokes_document.strokes[0].model_dump() == {
        "id": strokes[0].id,
        "order": 1,
        "points": [(0.05, 0.025), (0.55, 0.125)],
        "closed": False,
    }


def test_svg_reports_unsupported_and_fill_only_content() -> None:
    content = b'''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
      <path id="solid" d="M0 0 H10 V10 Z" fill="red"/>
      <text id="label" x="5" y="30">hello</text>
      <image id="embedded" href="data:image/png;base64,AA=="/>
      <image id="external" href="https://example.com/picture.png"/>
      <line id="filtered" x1="0" y1="50" x2="90" y2="50" stroke="black"
            filter="url(#blur)" clip-path="url(#clip)"/>
    </svg>'''

    result = process_svg(content, "warnings.svg", svg_parameters())

    assert result.audit_document.warnings == sorted(
        {
            "clip_path_ignored:filtered",
            "embedded_image_not_processed:embedded",
            "external_image_blocked:external",
            "fill_only_ignored:solid",
            "filter_ignored:filtered",
            "unsupported_text:label",
        }
    )
    assert len(result.audit_document.strokes) == 1


def test_svg_output_is_deterministic() -> None:
    content = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10">
      <polyline points="0,0 10,5 20,0" fill="none" stroke="black"/>
    </svg>'''
    first = process_svg(content, "same.svg", svg_parameters())
    second = process_svg(content, "same.svg", svg_parameters())
    assert first == second


def test_svg_is_centered_inside_explicit_physical_canvas() -> None:
    content = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">
      <line x1="0" y1="0" x2="200" y2="100" stroke="black"/>
    </svg>'''

    result = process_svg(
        content,
        "fitted.svg",
        svg_parameters(target_width_mm=200, target_height_mm=200),
    )

    assert result.audit_document.canvas.width == 1
    assert result.audit_document.canvas.height == 1
    assert result.audit_document.canvas.target_height_mm == 200
    assert result.audit_document.strokes[0].points == [(0.0, 0.25), (1.0, 0.75)]
