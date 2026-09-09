"""Offline planar AprilTag layout expansion from measured anchor tags."""

from __future__ import annotations

import math
from collections import defaultdict, deque

from .calibration import BoardLayout, VisionCalibrationError

try:
    import cv2
    import numpy as np
except ImportError as error:  # Keep non-vision console imports usable.
    cv2 = None
    np = None
    _IMPORT_ERROR = error
else:
    _IMPORT_ERROR = None


class BoardCalibrationError(ValueError):
    """Raised when observations cannot define one connected planar layout."""


def _require_opencv():
    if _IMPORT_ERROR is not None:
        raise VisionCalibrationError("opencv_with_aruco_is_required") from _IMPORT_ERROR
    if not hasattr(cv2, "aruco") or not hasattr(cv2.aruco, "DICT_APRILTAG_36h11"):
        raise VisionCalibrationError("opencv_apriltag_36h11_is_required")


def _finite_points(value, shape, field):
    try:
        points = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise BoardCalibrationError("%s_invalid" % field) from error
    if points.shape != shape or not np.all(np.isfinite(points)):
        raise BoardCalibrationError("%s_invalid" % field)
    return points


def detect_apriltag_pixels(image, *, min_tag_edge_px=12.0):
    """Return decoded tag IDs and canonical four pixel corners for one image."""
    _require_opencv()
    if image is None or not hasattr(image, "shape") or len(image.shape) not in {2, 3}:
        raise BoardCalibrationError("image_array_required")
    if len(image.shape) == 3:
        if image.shape[2] == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        elif image.shape[2] == 4:
            gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
        else:
            raise BoardCalibrationError("image_channel_count_unsupported")
    else:
        gray = image
    parameters = cv2.aruco.DetectorParameters()
    if hasattr(cv2.aruco, "CORNER_REFINE_APRILTAG"):
        parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_APRILTAG
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    detector = cv2.aruco.ArucoDetector(dictionary, parameters)
    detected_corners, detected_ids, rejected = detector.detectMarkers(gray)
    observations = []
    if detected_ids is not None:
        for raw_corners, raw_id in zip(detected_corners, detected_ids.reshape(-1)):
            corners = np.asarray(raw_corners, dtype=np.float64).reshape(4, 2)
            edges = [
                float(np.linalg.norm(corners[index] - corners[(index + 1) % 4]))
                for index in range(4)
            ]
            if min(edges) < float(min_tag_edge_px):
                continue
            observations.append({
                "id": int(raw_id),
                "corners_px": [[round(float(axis), 3) for axis in point] for point in corners],
                "min_edge_px": round(min(edges), 3),
            })
    observations.sort(key=lambda item: item["id"])
    return {
        "image_width": int(gray.shape[1]),
        "image_height": int(gray.shape[0]),
        "observations": observations,
        "rejected_candidate_count": len(rejected),
    }


def _parse_frames(document, expected_dictionary):
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise BoardCalibrationError("observation_schema_invalid")
    if document.get("dictionary") != expected_dictionary:
        raise BoardCalibrationError("observation_dictionary_mismatch")
    raw_frames = document.get("frames")
    if not isinstance(raw_frames, list) or not raw_frames:
        raise BoardCalibrationError("observation_frames_required")
    frames = []
    for frame_index, raw_frame in enumerate(raw_frames):
        if not isinstance(raw_frame, dict) or not isinstance(raw_frame.get("observations"), list):
            raise BoardCalibrationError("observation_frame_invalid")
        seen = set()
        observations = {}
        for raw_observation in raw_frame["observations"]:
            if not isinstance(raw_observation, dict):
                raise BoardCalibrationError("tag_observation_invalid")
            tag_id = raw_observation.get("id")
            if isinstance(tag_id, bool) or not isinstance(tag_id, int) or tag_id < 0 or tag_id in seen:
                raise BoardCalibrationError("tag_observation_id_invalid")
            seen.add(tag_id)
            observations[tag_id] = _finite_points(
                raw_observation.get("corners_px"), (4, 2), "tag_observation_corners"
            )
        if observations:
            frames.append({
                "index": frame_index,
                "station": str(raw_frame.get("station", "")),
                "observations": observations,
            })
    if not frames:
        raise BoardCalibrationError("no_detected_tags_in_observations")
    return frames


def _tag_size_from_anchors(anchor_board):
    sizes = []
    for corners in anchor_board.tag_corners.values():
        points = np.asarray(corners, dtype=np.float64)[:, :2]
        sizes.extend(
            float(np.linalg.norm(points[index] - points[(index + 1) % 4]))
            for index in range(4)
        )
    return float(np.median(np.asarray(sizes, dtype=np.float64)))


def _homography(source, destination):
    if len(source) < 4:
        return None
    matrix, _ = cv2.findHomography(
        np.asarray(source, dtype=np.float64),
        np.asarray(destination, dtype=np.float64),
        method=0,
    )
    if matrix is None or not np.all(np.isfinite(matrix)):
        return None
    if abs(float(np.linalg.det(matrix))) < 1e-12:
        return None
    return matrix


def _project(points, matrix):
    projected = cv2.perspectiveTransform(
        np.asarray(points, dtype=np.float64).reshape(1, -1, 2), matrix
    )
    return projected.reshape(-1, 2)


def _frame_image_to_board(frame, world_points, excluded_id):
    image_points = []
    board_points = []
    for tag_id, corners_px in frame["observations"].items():
        if tag_id == excluded_id or tag_id not in world_points:
            continue
        image_points.extend(corners_px.tolist())
        board_points.extend(world_points[tag_id].tolist())
    return _homography(image_points, board_points)


def _fit_square(raw_corners, tag_size_mm):
    template = np.asarray(
        [[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]],
        dtype=np.float64,
    ) * float(tag_size_mm)
    center = np.asarray(raw_corners, dtype=np.float64).mean(axis=0)
    centered = np.asarray(raw_corners, dtype=np.float64) - center
    covariance = template.T @ centered
    left, _, right = np.linalg.svd(covariance)
    rotation = right.T @ left.T
    if np.linalg.det(rotation) < 0:
        right[-1, :] *= -1
        rotation = right.T @ left.T
    return template @ rotation.T + center


def _robust_square(candidates, tag_size_mm, outlier_threshold_mm):
    if not candidates:
        return None, [], []
    preliminary = _fit_square(np.median(np.stack(candidates), axis=0), tag_size_mm)
    errors = np.asarray([
        math.sqrt(float(np.mean(np.sum((candidate - preliminary) ** 2, axis=1))))
        for candidate in candidates
    ])
    median = float(np.median(errors))
    mad = float(np.median(np.abs(errors - median)))
    robust_limit = median + 3.0 * max(1.4826 * mad, 0.05)
    limit = min(float(outlier_threshold_mm), max(0.25, robust_limit))
    accepted_indexes = [index for index, error in enumerate(errors) if error <= limit]
    accepted = [candidates[index] for index in accepted_indexes]
    if not accepted:
        return None, [], errors.tolist()
    fitted = _fit_square(np.median(np.stack(accepted), axis=0), tag_size_mm)
    final_errors = [
        math.sqrt(float(np.mean(np.sum((candidate - fitted) ** 2, axis=1))))
        for candidate in candidates
    ]
    return fitted, accepted_indexes, final_errors


def _connectivity(frames, target_ids, anchor_ids):
    graph = {tag_id: set() for tag_id in target_ids}
    for frame in frames:
        visible = sorted(set(frame["observations"]).intersection(target_ids))
        for first in visible:
            graph[first].update(tag_id for tag_id in visible if tag_id != first)
    reached = set(anchor_ids).intersection(target_ids)
    queue = deque(reached)
    while queue:
        current = queue.popleft()
        for neighbor in sorted(graph[current]):
            if neighbor not in reached:
                reached.add(neighbor)
                queue.append(neighbor)
    edges = sorted({(min(first, second), max(first, second)) for first in graph for second in graph[first]})
    return reached, edges


def _rounded_points(points, plane_z):
    return [[round(float(x), 6), round(float(y), 6), round(float(plane_z), 6)] for x, y in points]


def solve_board_layout(
    anchor_board: BoardLayout,
    observation_document,
    *,
    target_ids=None,
    layout_id="calibrated-layout-review-required",
    tag_size_mm=None,
    min_samples_per_tag=3,
    min_stations_per_tag=2,
    outlier_threshold_mm=5.0,
    refinement_iterations=8,
):
    """Expand a measured anchor layout into a connected coplanar tag board."""
    _require_opencv()
    if anchor_board.dictionary != "DICT_APRILTAG_36H11":
        raise BoardCalibrationError("board_dictionary_unsupported")
    if (
        min_samples_per_tag < 1
        or min_stations_per_tag < 1
        or refinement_iterations < 0
        or outlier_threshold_mm <= 0
    ):
        raise BoardCalibrationError("calibration_numeric_option_invalid")
    frames = _parse_frames(observation_document, anchor_board.dictionary)
    anchor_ids = set(anchor_board.tag_corners)
    detected_ids = {tag_id for frame in frames for tag_id in frame["observations"]}
    if target_ids is None:
        requested_ids = anchor_ids | detected_ids
    else:
        requested_ids = set(target_ids)
        if not requested_ids or any(isinstance(tag_id, bool) or not isinstance(tag_id, int) or tag_id < 0 for tag_id in requested_ids):
            raise BoardCalibrationError("target_ids_invalid")
        if not anchor_ids.issubset(requested_ids):
            raise BoardCalibrationError("target_ids_must_include_all_anchors")
    missing_detections = sorted(requested_ids - detected_ids - anchor_ids)
    if missing_detections:
        raise BoardCalibrationError("target_tags_never_detected:%s" % ",".join(map(str, missing_detections)))
    reached, edges = _connectivity(frames, requested_ids, anchor_ids)
    disconnected = sorted(requested_ids - reached)
    if disconnected:
        raise BoardCalibrationError("target_tags_not_connected_to_anchors:%s" % ",".join(map(str, disconnected)))

    inferred_size = _tag_size_from_anchors(anchor_board)
    size = inferred_size if tag_size_mm is None else float(tag_size_mm)
    if not math.isfinite(size) or size <= 0:
        raise BoardCalibrationError("tag_size_mm_invalid")
    z_values = [corner[2] for corners in anchor_board.tag_corners.values() for corner in corners]
    plane_z = float(np.median(np.asarray(z_values, dtype=np.float64)))
    world_points = {
        tag_id: np.asarray(corners, dtype=np.float64)[:, :2].copy()
        for tag_id, corners in anchor_board.tag_corners.items()
    }
    estimated_ids = sorted(requested_ids - anchor_ids)
    tag_stats = {}

    # Grow outward through overlapping frames, keeping measured anchors immutable.
    for _ in range(len(estimated_ids) + 1):
        added = False
        for tag_id in estimated_ids:
            if tag_id in world_points:
                continue
            candidates = []
            candidate_stations = []
            for frame in frames:
                if tag_id not in frame["observations"]:
                    continue
                image_to_board = _frame_image_to_board(frame, world_points, tag_id)
                if image_to_board is not None:
                    candidates.append(_project(frame["observations"][tag_id], image_to_board))
                    candidate_stations.append(frame["station"] or "frame-%d" % frame["index"])
            fitted, accepted, errors = _robust_square(candidates, size, outlier_threshold_mm)
            accepted_stations = {candidate_stations[index] for index in accepted}
            if fitted is not None and len(accepted) >= min_samples_per_tag:
                world_points[tag_id] = fitted
                tag_stats[tag_id] = (len(candidates), accepted, errors, accepted_stations)
                added = True
        if not added:
            break
    unresolved = sorted(requested_ids - set(world_points))
    if unresolved:
        raise BoardCalibrationError(
            "insufficient_overlap_samples_for_tags:%s" % ",".join(map(str, unresolved))
        )

    # Alternate per-frame homographies and rigid-square estimates. Anchors never move.
    for _ in range(refinement_iterations):
        maximum_shift = 0.0
        updates = {}
        for tag_id in estimated_ids:
            candidates = []
            candidate_stations = []
            for frame in frames:
                if tag_id not in frame["observations"]:
                    continue
                image_to_board = _frame_image_to_board(frame, world_points, tag_id)
                if image_to_board is not None:
                    candidates.append(_project(frame["observations"][tag_id], image_to_board))
                    candidate_stations.append(frame["station"] or "frame-%d" % frame["index"])
            fitted, accepted, errors = _robust_square(candidates, size, outlier_threshold_mm)
            accepted_stations = {candidate_stations[index] for index in accepted}
            if fitted is None or len(accepted) < min_samples_per_tag:
                raise BoardCalibrationError("insufficient_refinement_samples_for_tag:%d" % tag_id)
            if len(accepted_stations) < min_stations_per_tag:
                raise BoardCalibrationError("insufficient_distinct_stations_for_tag:%d" % tag_id)
            updates[tag_id] = fitted
            tag_stats[tag_id] = (len(candidates), accepted, errors, accepted_stations)
            maximum_shift = max(
                maximum_shift,
                float(np.linalg.norm(fitted.mean(axis=0) - world_points[tag_id].mean(axis=0))),
            )
        world_points.update(updates)
        if maximum_shift < 1e-5:
            break

    held_out_errors = defaultdict(list)
    usable_frames = set()
    for frame in frames:
        visible = sorted(set(frame["observations"]).intersection(world_points))
        if len(visible) < 2:
            continue
        usable_frames.add(frame["index"])
        for tag_id in visible:
            image_to_board = _frame_image_to_board(frame, world_points, tag_id)
            if image_to_board is None:
                continue
            predicted = _project(frame["observations"][tag_id], image_to_board)
            held_out_errors[tag_id].extend(
                np.linalg.norm(predicted - world_points[tag_id], axis=1).tolist()
            )

    report_tags = {}
    all_held_out = []
    for tag_id in sorted(requested_ids):
        points = world_points[tag_id]
        errors = held_out_errors[tag_id]
        all_held_out.extend(errors)
        entry = {
            "kind": "measured_anchor" if tag_id in anchor_ids else "estimated",
            "center_mm": [round(float(axis), 6) for axis in points.mean(axis=0)],
            "held_out_corner_rmse_mm": (
                round(math.sqrt(sum(error * error for error in errors) / len(errors)), 6)
                if errors else None
            ),
            "held_out_corner_count": len(errors),
        }
        if tag_id in tag_stats:
            sample_count, accepted_indexes, sample_errors, accepted_stations = tag_stats[tag_id]
            accepted_errors = [sample_errors[index] for index in accepted_indexes]
            entry.update({
                "candidate_frame_count": sample_count,
                "accepted_frame_count": len(accepted_indexes),
                "rejected_frame_count": sample_count - len(accepted_indexes),
                "accepted_station_count": len(accepted_stations),
                "accepted_stations": sorted(accepted_stations),
                "fit_sample_rmse_mm": round(
                    math.sqrt(sum(error * error for error in accepted_errors) / len(accepted_errors)), 6
                ),
            })
        report_tags[str(tag_id)] = entry

    board = {
        "schema_version": 1,
        "production_ready": False,
        "layout_id": str(layout_id),
        "frame": anchor_board.frame,
        "units": "mm",
        "dictionary": anchor_board.dictionary,
        "corner_order": "top_left_clockwise",
        "tags": {
            str(tag_id): {"corners": _rounded_points(world_points[tag_id], plane_z)}
            for tag_id in sorted(requested_ids)
        },
    }
    report = {
        "schema_version": 1,
        "status": "review_required",
        "layout_id": str(layout_id),
        "anchor_layout_id": anchor_board.layout_id,
        "frame": anchor_board.frame,
        "dictionary": anchor_board.dictionary,
        "tag_size_mm": round(size, 6),
        "tag_size_source": "anchor_median" if tag_size_mm is None else "explicit",
        "frame_count": len(frames),
        "station_count": len({frame["station"] for frame in frames if frame["station"]}),
        "stations": sorted({frame["station"] for frame in frames if frame["station"]}),
        "cross_validation_frame_count": len(usable_frames),
        "anchor_ids": sorted(anchor_ids),
        "estimated_ids": estimated_ids,
        "target_ids": sorted(requested_ids),
        "co_visible_edges": [[first, second] for first, second in edges],
        "cross_validated_corner_rmse_mm": (
            round(math.sqrt(sum(error * error for error in all_held_out) / len(all_held_out)), 6)
            if all_held_out else None
        ),
        "tags": report_tags,
        "notes": [
            "Measured anchor corners were held fixed.",
            "Estimated tags were constrained to one rigid square on the anchor plane.",
            "production_ready remains false until physical review and runtime validation.",
        ],
    }
    return board, report
