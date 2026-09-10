"""AprilTag-center rail displacement without a full camera pose solve."""

import math
import time

import cv2
import numpy as np


def _rounded(value, digits=6):
    return round(float(value), digits)


def _minimum_edge(corners):
    return min(
        float(np.linalg.norm(corners[(index + 1) % 4] - corners[index]))
        for index in range(4)
    )


def _polygon_area(corners):
    x = corners[:, 0]
    y = corners[:, 1]
    return abs(float(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))) * 0.5


class AprilTagCenterDeltaLocalizer:
    """Estimate one-dimensional camera travel from a stopped zero reference.

    At the reference position, four or more decoded tag centers define a
    pixel-to-board homography. With camera height and attitude fixed, rail-only
    camera translation is equivalent to translating board X or Y before that
    same homography. Each subsequently visible tag therefore yields an
    independent rail displacement estimate. No camera intrinsics or tag-corner
    orientation enter the estimate.
    """

    AXES = {"x": 0, "y": 1}

    def __init__(
        self,
        camera,
        board,
        reference,
        rail_axis="x",
        min_tag_edge_px=24.0,
        min_confidence=0.55,
        min_visible_tags=2,
    ):
        if rail_axis not in self.AXES:
            raise ValueError("center_delta_rail_axis_must_be_planar")
        self.camera = camera
        self.board = board
        self.reference = reference
        self.localization_method = "center_delta"
        self.rail_axis = rail_axis
        self.min_tag_edge_px = float(min_tag_edge_px)
        self.min_confidence = float(min_confidence)
        self.min_visible_tags = int(min_visible_tags)
        self.calibration_id = reference.reference_id
        self._sequence = 0
        self._board_centers = {
            tag_id: np.asarray(corners, dtype=np.float64)[:, :2].mean(axis=0)
            for tag_id, corners in board.tag_corners.items()
        }
        reference_ids = sorted(reference.tag_centers_px)
        if any(tag_id not in self._board_centers for tag_id in reference_ids):
            raise ValueError("center_reference_contains_unknown_tag")
        reference_pixels = np.asarray(
            [reference.tag_centers_px[tag_id] for tag_id in reference_ids],
            dtype=np.float64,
        )
        reference_world = np.asarray(
            [self._board_centers[tag_id] for tag_id in reference_ids],
            dtype=np.float64,
        )
        homography, _ = cv2.findHomography(reference_pixels, reference_world, 0)
        if homography is None or not np.all(np.isfinite(homography)):
            raise ValueError("center_reference_homography_unsolved")
        if abs(float(np.linalg.det(homography))) < 1e-12:
            raise ValueError("center_reference_homography_singular")
        self._pixel_to_board = homography
        self._board_to_pixel = np.linalg.inv(homography)

        parameters = cv2.aruco.DetectorParameters()
        if hasattr(cv2.aruco, "CORNER_REFINE_APRILTAG"):
            parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_APRILTAG
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
        self._detector = cv2.aruco.ArucoDetector(dictionary, parameters)

    def _scaled_center(self, center, width, height):
        reference_aspect = self.reference.image_width / self.reference.image_height
        frame_aspect = width / height
        if abs(reference_aspect - frame_aspect) / reference_aspect > 0.01:
            return None
        return np.asarray([
            center[0] * self.reference.image_width / width,
            center[1] * self.reference.image_height / height,
        ], dtype=np.float64)

    def process(self, image, timestamp_ms=None):
        if image is None or not hasattr(image, "shape") or len(image.shape) not in {2, 3}:
            raise ValueError("image_array_required")
        height, width = int(image.shape[0]), int(image.shape[1])
        if width <= 0 or height <= 0:
            raise ValueError("image_dimensions_invalid")
        if len(image.shape) == 3:
            if image.shape[2] == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            elif image.shape[2] == 4:
                gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
            else:
                raise ValueError("image_channel_count_unsupported")
        else:
            gray = image

        self._sequence += 1
        captured_ms = int(time.time() * 1000) if timestamp_ms is None else int(timestamp_ms)
        started = time.perf_counter()
        detected_corners, detected_ids, rejected = self._detector.detectMarkers(gray)
        observations = []
        usable = []
        if detected_ids is not None:
            for raw_corners, raw_id in zip(detected_corners, detected_ids.reshape(-1)):
                tag_id = int(raw_id)
                corners = np.asarray(raw_corners, dtype=np.float64).reshape(4, 2)
                center = corners.mean(axis=0)
                known = tag_id in self._board_centers
                observation = {
                    "id": tag_id,
                    "known": known,
                    "corners_px": [[_rounded(axis, 3) for axis in point] for point in corners.tolist()],
                    "center_px": [_rounded(axis, 3) for axis in center.tolist()],
                    "min_edge_px": _rounded(_minimum_edge(corners), 3),
                    "area_px2": _rounded(_polygon_area(corners), 3),
                }
                observations.append(observation)
                if known and observation["min_edge_px"] >= self.min_tag_edge_px:
                    scaled = self._scaled_center(center, width, height)
                    if scaled is None:
                        return self._result(
                            started, captured_ms, width, height, observations, rejected,
                            "calibration_mismatch", "reference_resolution_aspect_mismatch",
                        )
                    usable.append((observation, scaled))

        if not usable:
            status = "unknown_tags" if observations else "no_tags"
            error = "no_known_tag_visible" if observations else "none"
            return self._result(
                started, captured_ms, width, height, observations, rejected,
                status, error,
            )

        pixels = np.asarray([item[1] for item in usable], dtype=np.float64)
        mapped = cv2.perspectiveTransform(
            pixels.reshape(-1, 1, 2), self._pixel_to_board
        ).reshape(-1, 2)
        rail_index = self.AXES[self.rail_axis]
        cross_index = 1 - rail_index
        deltas = []
        cross_errors = []
        for (observation, _), mapped_center in zip(usable, mapped):
            world_center = self._board_centers[observation["id"]]
            delta = float(world_center[rail_index] - mapped_center[rail_index])
            cross_error = float(mapped_center[cross_index] - world_center[cross_index])
            deltas.append(delta)
            cross_errors.append(cross_error)
            observation["rail_delta_mm"] = _rounded(delta, 3)
            observation["cross_axis_error_mm"] = _rounded(cross_error, 3)

        rail_delta = float(np.median(np.asarray(deltas, dtype=np.float64)))
        tag_disagreement = max(deltas) - min(deltas)
        max_cross_error = max(abs(value) for value in cross_errors)
        predicted_world = []
        for observation, _ in usable:
            point = self._board_centers[observation["id"]].copy()
            point[rail_index] -= rail_delta
            predicted_world.append(point)
        predicted_pixels = cv2.perspectiveTransform(
            np.asarray(predicted_world, dtype=np.float64).reshape(-1, 1, 2),
            self._board_to_pixel,
        ).reshape(-1, 2)
        pixel_rmse = math.sqrt(float(np.mean(np.sum((predicted_pixels - pixels) ** 2, axis=1))))

        edge_score = min(
            1.0,
            min(item[0]["min_edge_px"] for item in usable) / self.min_tag_edge_px,
        )
        count_score = min(1.0, len(usable) / max(1, self.min_visible_tags))
        disagreement_score = max(
            0.0,
            1.0 - tag_disagreement / self.reference.max_tag_disagreement_mm,
        )
        cross_score = max(
            0.0,
            1.0 - max_cross_error / self.reference.max_cross_axis_error_mm,
        )
        components = {
            "tag_size": edge_score,
            "known_tag_count": count_score,
            "tag_agreement": disagreement_score,
            "cross_axis": cross_score,
        }
        confidence = sum(components.values()) / len(components)
        enough_tags = len(usable) >= self.min_visible_tags
        quality_ok = (
            tag_disagreement <= self.reference.max_tag_disagreement_mm
            and max_cross_error <= self.reference.max_cross_axis_error_mm
        )
        ready = bool(self.reference.production_ready)
        accepted = ready and enough_tags and quality_ok and confidence >= self.min_confidence
        if accepted:
            status, error = "accepted", "none"
        elif not ready:
            status, error = "precalibration", "center_reference_unverified"
        elif not enough_tags:
            status, error = "insufficient_tags", "insufficient_visible_tags"
        elif not quality_ok:
            status, error = "position_rejected", "center_delta_quality_invalid"
        else:
            status, error = "low_confidence", "confidence_below_threshold"
        result = self._result(
            started, captured_ms, width, height, observations, rejected,
            status, error,
        )
        result.update(
            position_solved=True,
            accepted=accepted,
            confidence=_rounded(confidence, 4),
            confidence_threshold=self.min_confidence,
            reprojection_rmse_px=_rounded(pixel_rmse, 4),
            score_components={key: _rounded(value, 4) for key, value in components.items()},
            used_ids=sorted(item[0]["id"] for item in usable),
            rail_position_mm=_rounded(rail_delta, 6),
            rail_delta_mm=_rounded(rail_delta, 6),
            tag_disagreement_mm=_rounded(tag_disagreement, 6),
            max_cross_axis_error_mm=_rounded(max_cross_error, 6),
        )
        result["processing_ms"] = _rounded((time.perf_counter() - started) * 1000, 3)
        return result

    def _result(
        self, started, captured_ms, width, height, observations, rejected,
        status, error,
    ):
        return {
            "enabled": True,
            "status": status,
            "error": error,
            "frame_sequence": self._sequence,
            "captured_at_ms": captured_ms,
            "image_width": width,
            "image_height": height,
            "dictionary": "DICT_APRILTAG_36H11",
            "layout_id": self.board.layout_id,
            "board_frame": self.board.frame,
            "calibration_id": self.reference.reference_id,
            "localization_method": "center_delta",
            "camera_calibration_ready": self.camera.production_ready,
            "board_layout_ready": self.board.production_ready,
            "rail_reference_ready": self.reference.production_ready,
            "detected_count": len(observations),
            "known_count": sum(bool(item["known"]) for item in observations),
            "rejected_candidate_count": len(rejected),
            "observations": observations,
            "pose_solved": False,
            "position_solved": False,
            "accepted": False,
            "confidence": 0.0,
            "confidence_kind": "quality_score_not_probability",
            "confidence_threshold": self.min_confidence,
            "reprojection_rmse_px": None,
            "score_components": {},
            "used_ids": [],
            "rail_position_mm": None,
            "processing_ms": _rounded((time.perf_counter() - started) * 1000, 3),
        }
