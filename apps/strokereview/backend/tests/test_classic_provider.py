from __future__ import annotations

import math
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw

import app.classic_provider as classic_provider
from app.classic_provider import (
    Branch,
    _combine_branches,
    _extract_atomic_branches,
    _mark_near_duplicate_strokes,
    _mark_outer_contour_candidates,
    _join_physical_gaps,
    _physical_importance_selection,
    _max_distance_to_polyline,
    _outer_contour_distance_map,
    _outline_likelihood,
    _prepare_color_sampling_image,
    _two_sided_color_contrast,
    _smooth_and_simplify,
    decode_raster,
    extract_classic_lineart,
    process_classic,
    trace_skeleton,
    TracedPath,
)
from app.models import AuditScores, AuditStroke, CanvasSpec, Decision, ProcessingParameters


def drawing_bytes(shape: str) -> bytes:
    image = Image.new("RGB", (256, 256), "white")
    draw = ImageDraw.Draw(image)
    if shape in {"line", "cross"}:
        draw.line((30, 128, 226, 128), fill="black", width=5)
    if shape == "cross":
        draw.line((128, 30, 128, 226), fill="black", width=5)
    elif shape == "circle":
        draw.ellipse((40, 40, 216, 216), outline="black", width=5)
    elif shape == "short":
        draw.line((126, 128, 131, 128), fill="black", width=1)
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def classic_parameters(**updates) -> ProcessingParameters:
    values = {"provider": "classic", "smoothing": 0}
    values.update(updates)
    return ProcessingParameters(**values)


def test_decode_downsamples_before_creating_processing_array() -> None:
    image = Image.new("RGB", (4000, 2000), "white")
    output = BytesIO()
    image.save(output, "PNG")

    decoded, source_width, source_height = decode_raster(output.getvalue(), max_dimension=512)

    assert (source_width, source_height) == (4000, 2000)
    assert decoded.shape == (256, 512, 3)


def test_straight_line_produces_one_keep_stroke() -> None:
    result = process_classic(drawing_bytes("line"), "line.png", classic_parameters())
    assert len(result.audit_document.strokes) == 1
    assert result.audit_document.strokes[0].decision == Decision.KEEP
    assert len(result.strokes_document.strokes) == 1
    assert result.diagnostics is not None


def test_cross_pairs_into_two_continuous_strokes() -> None:
    result = process_classic(drawing_bytes("cross"), "cross.png", classic_parameters())
    assert len(result.audit_document.strokes) == 2
    assert all(stroke.decision == Decision.KEEP for stroke in result.audit_document.strokes)


def test_circle_is_closed() -> None:
    result = process_classic(drawing_bytes("circle"), "circle.png", classic_parameters())
    assert len(result.audit_document.strokes) == 1
    assert result.audit_document.strokes[0].closed is True


def test_short_isolated_line_is_discarded_but_retained_in_audit() -> None:
    result = process_classic(
        drawing_bytes("short"),
        "short.png",
        classic_parameters(minimum_length_mm=10, effective_resolution_mm=0.1),
    )
    assert len(result.audit_document.strokes) == 1
    assert result.audit_document.strokes[0].decision == Decision.DISCARD
    assert "too_short_isolated" in result.audit_document.strokes[0].reasons
    assert result.strokes_document.strokes == []


def test_classic_output_is_deterministic() -> None:
    content = drawing_bytes("cross")
    first = process_classic(content, "cross.png", classic_parameters())
    second = process_classic(content, "cross.png", classic_parameters())
    assert first == second


def test_unsafe_spline_falls_back_instead_of_exporting_a_long_jump() -> None:
    # This short point sequence used to make SciPy's smoothed result oscillate and
    # emit 66 points with a final segment over 13 times the local median length.
    points = np.array(
        [
            [0.0, 0.0],
            [1.4208337923, 3.8438866146],
            [71.2469299395, -0.2729321442],
            [69.7600194424, -1.4939801049],
            [70.8874327236, -1.3554704096],
            [96.5307907450, 45.1300630341],
        ],
        dtype=np.float64,
    )

    result = _smooth_and_simplify(
        points,
        False,
        classic_parameters(detail_level=100, smoothing=100),
    )

    # Unsafe spline resampling must be rejected. The safe fallback may add points
    # only to enforce max_segment_length_mm; it cannot emit a large jump.
    assert np.all(np.isfinite(result))
    np.testing.assert_allclose(result[0], points[0], atol=1e-5)
    np.testing.assert_allclose(result[-1], points[-1], atol=1e-5)
    assert float(np.max(np.linalg.norm(np.diff(result, axis=0), axis=1))) <= 3.0 + 1e-6


def test_normal_open_curve_remains_smooth_and_keeps_exact_endpoints() -> None:
    x = np.linspace(0, 100, 101)
    points = np.column_stack((x, 20 * np.sin(x / 20)))

    result = _smooth_and_simplify(
        points,
        False,
        classic_parameters(detail_level=100, smoothing=50),
    )

    assert len(result) > 10
    np.testing.assert_allclose(result[0], points[0], atol=1e-8)
    np.testing.assert_allclose(result[-1], points[-1], atol=1e-5)
    segments = np.linalg.norm(np.diff(result, axis=0), axis=1)
    assert float(np.max(segments)) <= float(np.median(segments)) * 3


def test_branch_combiner_refuses_a_forced_distant_connection(monkeypatch) -> None:
    branches = [
        Branch(id=0, points=np.array([[0.0, 0.0], [1.0, 0.0]])),
        Branch(id=1, points=np.array([[100.0, 0.0], [101.0, 0.0]])),
    ]
    # Simulate a corrupted/future pairing implementation. The combiner itself
    # must still prevent a line from being drawn across the 99-pixel gap.
    monkeypatch.setattr(
        classic_provider,
        "_junction_pairs",
        lambda _branches: {(0, 1): (1, 0), (1, 0): (0, 1)},
    )

    combined = _combine_branches(branches)

    assert len(combined) == 2
    assert all(
        float(np.max(np.linalg.norm(np.diff(points, axis=0), axis=1))) <= np.sqrt(2)
        for points, _closed in combined
    )


def skeleton_parameters(**updates) -> ProcessingParameters:
    values = {
        "provider": "classic",
        "spur_prune_length_mm": 1.2,
        "smooth_tolerance_mm": 0.30,
        "geometry_tolerance_mm": 0.20,
        "max_segment_length_mm": 3.0,
    }
    values.update(updates)
    return ProcessingParameters(**values)


def traced(skeleton: np.ndarray, *, mm_per_pixel: float = 0.2):
    confidence = np.where(skeleton, 1.0, 0.0).astype(np.float32)
    return trace_skeleton(
        skeleton,
        mm_per_pixel=mm_per_pixel,
        confidence_map=confidence,
        parameters=skeleton_parameters(),
    )


def test_junction_pixel_cluster_becomes_one_logical_x_node() -> None:
    skeleton = np.zeros((41, 41), dtype=bool)
    for offset in range(5, 36):
        skeleton[offset, offset] = True
        skeleton[offset, 40 - offset] = True

    branches = _extract_atomic_branches(skeleton)

    assert len(branches) == 4
    junction_nodes = [
        node
        for branch in branches
        for node in (branch.start_node, branch.end_node)
        if node is not None
    ]
    assert max(junction_nodes.count(node) for node in set(junction_nodes)) == 4
    paths = traced(skeleton)
    assert len(paths) == 2
    assert all(not path.closed for path in paths)


def test_junction_cluster_internal_triangle_is_not_exported_as_a_closed_stroke() -> None:
    # Three mutually adjacent pixels form a tiny 8-neighbour triangle at a T
    # junction. Skan sees a cycle if the raw junction pixels are traced first.
    skeleton = np.zeros((25, 25), dtype=bool)
    skeleton[10, 10] = True
    skeleton[10, 11] = True
    skeleton[11, 10] = True
    skeleton[10, 2:10] = True
    skeleton[10, 12:21] = True
    skeleton[12:21, 10] = True

    branches = _extract_atomic_branches(skeleton)
    combined = _combine_branches(branches)

    assert len(branches) == 3
    assert all(branch.start_node != branch.end_node for branch in branches)
    assert len(combined) == 2
    assert all(not closed for _points, closed in combined)


def test_short_terminal_spur_is_pruned_before_pairing_and_retained_for_audit() -> None:
    skeleton = np.zeros((41, 41), dtype=bool)
    skeleton[20, 4:37] = True
    skeleton[18:20, 20] = True  # 0.4 mm leaf-to-junction spur

    paths = traced(skeleton)

    main = [path for path in paths if "pruned_spur" not in path.reasons]
    pruned = [path for path in paths if "pruned_spur" in path.reasons]
    assert len(main) == 1
    assert len(pruned) == 1
    assert pruned[0].decision_hint == Decision.DISCARD


def test_real_short_branch_is_not_deleted_on_length_alone() -> None:
    skeleton = np.zeros((41, 41), dtype=bool)
    skeleton[20, 4:37] = True
    skeleton[15:20, 20] = True  # 1.0 mm branch with the same line confidence

    paths = traced(skeleton)

    assert all("pruned_spur" not in path.reasons for path in paths)
    assert len(paths) == 2  # T: straight bar plus real short stem


def test_t_junction_and_closed_loop_topology_survive_graph_cleanup() -> None:
    tee = np.zeros((41, 41), dtype=bool)
    tee[20, 4:37] = True
    tee[6:21, 20] = True
    tee_paths = traced(tee)
    assert len(tee_paths) == 2
    assert all(not path.closed for path in tee_paths)

    loop = np.zeros((41, 41), dtype=bool)
    loop[6, 6:35] = True
    loop[34, 6:35] = True
    loop[6:35, 6] = True
    loop[6:35, 34] = True
    loop_paths = traced(loop)
    assert len(loop_paths) == 1
    assert loop_paths[0].closed is True


def test_gentle_pixel_zigzag_is_smoothed_and_reduced_by_more_than_sixty_percent() -> None:
    x = np.arange(0.0, 201.0)
    staircase = np.where((np.arange(len(x)) % 2) == 0, -0.8, 0.8)
    points = np.column_stack((x, 40.0 + 12.0 * np.sin(x / 55.0) + staircase))
    parameters = skeleton_parameters(smoothing=25)

    result = _smooth_and_simplify(points, False, parameters, mm_per_pixel=0.2)

    old_fixed_sampling_count = max(
        len(points),
        math.ceil(float(np.sum(np.linalg.norm(np.diff(points, axis=0), axis=1))) / 2),
    )
    assert len(result) <= old_fixed_sampling_count * 0.40
    assert _max_distance_to_polyline(result, points) <= 1.5 + 1e-6  # 0.30 mm
    assert float(np.max(np.linalg.norm(np.diff(result, axis=0), axis=1))) <= 15.0 + 1e-6


def test_geometry_density_is_independent_of_detail_level() -> None:
    x = np.arange(0.0, 121.0)
    points = np.column_stack((x, 20.0 + 8.0 * np.sin(x / 30.0)))

    low = _smooth_and_simplify(
        points,
        False,
        skeleton_parameters(detail_level=0),
        mm_per_pixel=0.2,
    )
    high = _smooth_and_simplify(
        points,
        False,
        skeleton_parameters(detail_level=100),
        mm_per_pixel=0.2,
    )

    np.testing.assert_allclose(low, high)


def test_black_background_white_line_uses_correct_confidence_polarity() -> None:
    parameters = skeleton_parameters(effective_resolution_mm=0.1)
    dark = np.zeros((128, 128, 3), dtype=np.uint8)
    dark[62:67, 16:112] = 255
    light = 255 - dark

    dark_mask, dark_confidence = extract_classic_lineart(dark, parameters)
    light_mask, light_confidence = extract_classic_lineart(light, parameters)

    assert dark_mask[64, 64] and light_mask[64, 64]
    assert dark_confidence[64, 64] > dark_confidence[10, 10]
    assert light_confidence[64, 64] > light_confidence[10, 10]
    assert dark_confidence[64, 64] > 0.8
    assert light_confidence[64, 64] > 0.8


def audit_line(stroke_id: str, y: float) -> AuditStroke:
    return AuditStroke(
        id=stroke_id,
        source="raster",
        points=[(0.1, y), (0.9, y)],
        closed=False,
        confidence=0.9,
        decision=Decision.KEEP,
        scores=AuditScores(risk=0.1, line_confidence=0.9),
        length_mm=168.0,
    )


def square_canvas() -> CanvasSpec:
    return CanvasSpec(
        width=1.0,
        height=1.0,
        source_width=1000,
        source_height=1000,
        source_aspect_ratio=1.0,
        target_width_mm=210.0,
        target_height_mm=210.0,
    )


def test_near_duplicate_parallel_stroke_is_recoverable_uncertain() -> None:
    strokes = [audit_line("stroke_a", 0.1000), audit_line("stroke_b", 0.1010)]

    _mark_near_duplicate_strokes(strokes, square_canvas(), skeleton_parameters())

    assert [stroke.decision for stroke in strokes].count(Decision.KEEP) == 1
    uncertain = next(stroke for stroke in strokes if stroke.decision == Decision.UNCERTAIN)
    assert "near_duplicate_parallel" in uncertain.reasons
    assert uncertain.reversible is True


def test_resolvable_parallel_lines_are_not_marked_as_duplicates() -> None:
    # 0.01 normalized units = 2.1 mm, safely above the default 0.5 mm
    # pen/effective-resolution threshold.
    strokes = [audit_line("stroke_a", 0.1000), audit_line("stroke_b", 0.1100)]

    _mark_near_duplicate_strokes(strokes, square_canvas(), skeleton_parameters())

    assert all(stroke.decision == Decision.KEEP for stroke in strokes)


def test_pen_diameter_controls_safe_parallel_overlap_detection() -> None:
    # 0.007 normalized units = 1.47 mm on a 210 mm square canvas.
    strokes = [audit_line("stroke_a", 0.100), audit_line("stroke_b", 0.107)]

    _mark_near_duplicate_strokes(
        strokes,
        square_canvas(),
        skeleton_parameters(pen_width_mm=2.0),
    )

    assert [stroke.decision for stroke in strokes].count(Decision.UNCERTAIN) == 1


def test_outer_contour_score_rejects_internal_detail() -> None:
    mask = np.zeros((128, 128), dtype=np.uint8)
    cv2 = classic_provider.cv2
    cv2.rectangle(mask, (15, 15), (112, 112), 1, 3)
    cv2.circle(mask, (64, 64), 12, 1, 3)

    distance = _outer_contour_distance_map(mask, mm_per_pixel=0.25)
    outer = np.asarray([(x, 15) for x in range(15, 113)], dtype=np.float64)
    inner = np.asarray([(x, 64) for x in range(52, 77)], dtype=np.float64)

    assert _outline_likelihood(outer, distance, 3.0) > 0.75
    assert _outline_likelihood(inner, distance, 3.0) < 0.25


def test_two_sided_color_contrast_rejects_line_inside_same_color() -> None:
    image = np.full((128, 128, 3), 255, dtype=np.uint8)
    image[20:108, 20:108] = (210, 70, 70)
    # 黑色内部墨线本身不应制造“颜色边界”：采样看的是墨线两侧色块。
    image[62:67, 30:98] = 0
    lab = _prepare_color_sampling_image(image)
    outer_boundary = np.asarray([(20, y) for y in range(24, 104)], dtype=np.float64)
    internal_line = np.asarray([(x, 64) for x in range(30, 98)], dtype=np.float64)

    outer_score = _two_sided_color_contrast(outer_boundary, lab, 5.0)
    internal_score = _two_sided_color_contrast(internal_line, lab, 5.0)

    assert outer_score > 0.7
    assert internal_score < 0.1


def test_outer_contour_candidates_do_not_change_default_decisions() -> None:
    outer = audit_line("outer", 0.1)
    outer.scores.outline_likelihood = 0.9
    inner = audit_line("inner", 0.5)
    inner.scores.outline_likelihood = 0.2
    inner.decision = Decision.UNCERTAIN

    _mark_outer_contour_candidates([outer, inner], skeleton_parameters())

    assert "outer_contour_candidate" in outer.reasons
    assert "outer_contour_candidate" not in inner.reasons
    assert outer.decision == Decision.KEEP
    assert inner.decision == Decision.UNCERTAIN


def test_color_required_outline_candidates_exclude_near_color_sides() -> None:
    contrasting = audit_line("contrasting", 0.1)
    contrasting.scores.outline_likelihood = 0.8
    contrasting.scores.color_contrast = 0.7
    near_color = audit_line("near-color", 0.2)
    near_color.scores.outline_likelihood = 0.95
    near_color.scores.color_contrast = 0.02

    _mark_outer_contour_candidates(
        [contrasting, near_color],
        skeleton_parameters(provider="pidinet"),
        require_color_separation=True,
    )

    assert "outer_contour_candidate" in contrasting.reasons
    assert "outer_contour_candidate" not in near_color.reasons


def test_small_collinear_gap_inside_pen_footprint_is_joined() -> None:
    mask = np.zeros((32, 32), dtype=np.uint8)
    mask[10, 2:10] = 1
    mask[10, 12:22] = 1
    paths = [
        TracedPath(points=np.asarray([[2.0, 10.0], [9.0, 10.0]]), closed=False),
        TracedPath(points=np.asarray([[12.0, 10.0], [21.0, 10.0]]), closed=False),
    ]

    joined = _join_physical_gaps(
        paths,
        mask,
        mm_per_pixel=0.2,
        parameters=skeleton_parameters(pen_width_mm=1.0),
    )

    assert len(joined) == 1
    assert "physical_gap_join" in joined[0].reasons
    np.testing.assert_allclose(joined[0].points[[0, -1]], [[2.0, 10.0], [21.0, 10.0]])


def test_nearby_parallel_endpoints_are_not_gap_joined() -> None:
    mask = np.zeros((32, 32), dtype=np.uint8)
    mask[10, 2:10] = 1
    mask[12, 9:20] = 1
    paths = [
        TracedPath(points=np.asarray([[2.0, 10.0], [9.0, 10.0]]), closed=False),
        TracedPath(points=np.asarray([[9.0, 12.0], [19.0, 12.0]]), closed=False),
    ]

    joined = _join_physical_gaps(
        paths,
        mask,
        mm_per_pixel=0.2,
        parameters=skeleton_parameters(pen_width_mm=1.0),
    )

    assert len(joined) == 2


def test_physical_selection_obeys_max_strokes_and_keeps_exclusions_recoverable() -> None:
    strokes = [audit_line(f"stroke_{index}", 0.1 + index * 0.15) for index in range(4)]
    for index, stroke in enumerate(strokes):
        stroke.scores.outline_likelihood = 1.0 - index * 0.1
        stroke.scores.color_contrast = 1.0
    summary = _physical_importance_selection(
        strokes,
        square_canvas(),
        skeleton_parameters(max_strokes=2, detail_level=100, minimum_length_mm=0),
    )

    assert summary.automatic_keep_count <= 2
    assert sum(stroke.decision == Decision.KEEP for stroke in strokes) <= 2
    excluded = [stroke for stroke in strokes if "max_strokes_excluded" in stroke.reasons]
    assert excluded
    assert all(stroke.decision == Decision.UNCERTAIN and stroke.reversible for stroke in excluded)
    assert [stroke.importance_rank for stroke in strokes if stroke.importance_rank] == sorted(
        stroke.importance_rank for stroke in strokes if stroke.importance_rank
    )
