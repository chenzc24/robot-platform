"""AprilTag 36h11 detection and planar board-to-camera pose estimation."""

import math
import time

from .calibration import VisionCalibrationError

try:
    import cv2
    import numpy as np
except ImportError as error:  # Keep the console usable when vision is disabled.
    cv2 = None
    np = None
    _IMPORT_ERROR = error
else:
    _IMPORT_ERROR = None


def _rounded(value, digits=6):
    return round(float(value), digits)


def _matrix_list(value):
    return [[_rounded(axis) for axis in row] for row in value.tolist()]


def _vector_list(value):
    return [_rounded(axis) for axis in value.reshape(-1).tolist()]


def _polygon_area(corners):
    x = corners[:, 0]
    y = corners[:, 1]
    return abs(float(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))) * 0.5


def _minimum_edge(corners):
    return min(float(np.linalg.norm(corners[index] - corners[(index + 1) % 4])) for index in range(4))


class AprilTagBoardLocalizer:
    """Detect known tags and estimate T_camera_from_board for one image."""

    def __init__(
        self,
        camera,
        board,
        *,
        min_tag_edge_px=24.0,
        max_reprojection_error_px=5.0,
        min_confidence=0.55,
    ):
        if _IMPORT_ERROR is not None:
            raise VisionCalibrationError("opencv_with_aruco_is_required") from _IMPORT_ERROR
        if not hasattr(cv2, "aruco") or not hasattr(cv2.aruco, "DICT_APRILTAG_36h11"):
            raise VisionCalibrationError("opencv_apriltag_36h11_is_required")
        if board.dictionary != "DICT_APRILTAG_36H11":
            raise VisionCalibrationError("board_dictionary_unsupported")
        self.camera = camera
        self.board = board
        self.min_tag_edge_px = float(min_tag_edge_px)
        self.max_reprojection_error_px = float(max_reprojection_error_px)
        self.min_confidence = float(min_confidence)
        parameters = cv2.aruco.DetectorParameters()
        if hasattr(cv2.aruco, "CORNER_REFINE_APRILTAG"):
            parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_APRILTAG
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
        self._detector = cv2.aruco.ArucoDetector(dictionary, parameters)
        self._sequence = 0

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
        known_image_points = []
        known_object_points = []
        known_observation_indexes = []
        if detected_ids is not None:
            for raw_corners, raw_id in zip(detected_corners, detected_ids.reshape(-1)):
                tag_id = int(raw_id)
                corners = np.asarray(raw_corners, dtype=np.float64).reshape(4, 2)
                known = tag_id in self.board.tag_corners
                observation = {
                    "id": tag_id,
                    "known": known,
                    "corners_px": [[_rounded(axis, 3) for axis in point] for point in corners.tolist()],
                    "center_px": [_rounded(axis, 3) for axis in corners.mean(axis=0).tolist()],
                    "min_edge_px": _rounded(_minimum_edge(corners), 3),
                    "area_px2": _rounded(_polygon_area(corners), 3),
                }
                observations.append(observation)
                if known:
                    known_observation_indexes.append(len(observations) - 1)
                    known_image_points.extend(corners.tolist())
                    known_object_points.extend(self.board.tag_corners[tag_id])
        result = {
            "enabled": True,
            "status": "no_tags",
            "error": "none",
            "frame_sequence": self._sequence,
            "captured_at_ms": captured_ms,
            "image_width": width,
            "image_height": height,
            "dictionary": "DICT_APRILTAG_36H11",
            "layout_id": self.board.layout_id,
            "board_frame": self.board.frame,
            "calibration_id": self.camera.calibration_id,
            "camera_calibration_ready": self.camera.production_ready,
            "board_layout_ready": self.board.production_ready,
            "detected_count": len(observations),
            "known_count": len(known_observation_indexes),
            "rejected_candidate_count": len(rejected),
            "observations": observations,
            "pose_solved": False,
            "accepted": False,
            "confidence": 0.0,
            "confidence_kind": "quality_score_not_probability",
            "confidence_threshold": self.min_confidence,
            "reprojection_rmse_px": None,
            "score_components": {},
            "used_ids": [],
            "T_camera_from_board": None,
            "T_board_from_camera": None,
            "rvec_board_to_camera": None,
            "tvec_board_origin_in_camera_mm": None,
        }
        if not observations:
            result["processing_ms"] = _rounded((time.perf_counter() - started) * 1000, 3)
            return result
        if not known_image_points:
            result.update(status="unknown_tags", error="no_known_tag_visible")
            result["processing_ms"] = _rounded((time.perf_counter() - started) * 1000, 3)
            return result
        camera_matrix = self._scaled_camera_matrix(width, height)
        if camera_matrix is None:
            result.update(status="calibration_mismatch", error="calibration_resolution_aspect_mismatch")
            result["processing_ms"] = _rounded((time.perf_counter() - started) * 1000, 3)
            return result
        object_points = np.asarray(known_object_points, dtype=np.float64).reshape(-1, 3)
        image_points = np.asarray(known_image_points, dtype=np.float64).reshape(-1, 2)
        distortion = np.asarray(self.camera.distortion_coefficients, dtype=np.float64)
        pose = self._solve_planar_pose(object_points, image_points, camera_matrix, distortion)
        if pose is None:
            result.update(status="pose_failed", error="planar_pose_unsolved")
            result["processing_ms"] = _rounded((time.perf_counter() - started) * 1000, 3)
            return result
        rvec, tvec, projected, rmse = pose
        rotation, _ = cv2.Rodrigues(rvec)
        transform = np.eye(4, dtype=np.float64)
        transform[:3, :3] = rotation
        transform[:3, 3] = tvec.reshape(3)
        inverse = np.linalg.inv(transform)
        errors = np.linalg.norm(projected.reshape(-1, 2) - image_points, axis=1).reshape(-1, 4)
        for row, observation_index in enumerate(known_observation_indexes):
            observations[observation_index]["reprojection_rmse_px"] = _rounded(math.sqrt(float(np.mean(errors[row] ** 2))), 3)
        components = self._score(observations, known_observation_indexes, width, height, rmse)
        confidence = sum(components.values()) / len(components)
        finite_pose = bool(np.all(np.isfinite(transform)))
        positive_depth = bool(np.all((rotation @ object_points.T + tvec.reshape(3, 1))[2] > 0))
        reprojection_ok = rmse <= self.max_reprojection_error_px
        calibration_ready = self.camera.production_ready and self.board.production_ready
        accepted = calibration_ready and finite_pose and positive_depth and reprojection_ok and confidence >= self.min_confidence
        if accepted:
            status, error = "accepted", "none"
        elif not positive_depth or not finite_pose:
            status, error = "pose_rejected", "pose_geometry_invalid"
        elif not reprojection_ok:
            status, error = "pose_rejected", "reprojection_error_too_high"
        elif not calibration_ready:
            status, error = "precalibration", "calibration_inputs_unverified"
        else:
            status, error = "low_confidence", "confidence_below_threshold"
        result.update(
            status=status,
            error=error,
            pose_solved=True,
            accepted=accepted,
            confidence=_rounded(confidence, 4),
            reprojection_rmse_px=_rounded(rmse, 4),
            score_components={key: _rounded(value, 4) for key, value in components.items()},
            used_ids=sorted({observations[index]["id"] for index in known_observation_indexes}),
            T_camera_from_board=_matrix_list(transform),
            T_board_from_camera=_matrix_list(inverse),
            rvec_board_to_camera=_vector_list(rvec),
            tvec_board_origin_in_camera_mm=_vector_list(tvec),
        )
        result["processing_ms"] = _rounded((time.perf_counter() - started) * 1000, 3)
        return result

    def _scaled_camera_matrix(self, width, height):
        source_aspect = self.camera.image_width / self.camera.image_height
        frame_aspect = width / height
        if abs(source_aspect - frame_aspect) / source_aspect > 0.01:
            return None
        scale_x = width / self.camera.image_width
        scale_y = height / self.camera.image_height
        matrix = np.asarray(self.camera.camera_matrix, dtype=np.float64).copy()
        matrix[0, 0] *= scale_x
        matrix[0, 2] *= scale_x
        matrix[1, 1] *= scale_y
        matrix[1, 2] *= scale_y
        return matrix

    @staticmethod
    def _solve_planar_pose(object_points, image_points, camera_matrix, distortion):
        try:
            solved = cv2.solvePnPGeneric(
                object_points,
                image_points,
                camera_matrix,
                distortion,
                flags=cv2.SOLVEPNP_IPPE,
            )
        except cv2.error:
            return None
        if not solved[0]:
            return None
        candidates = []
        for rvec, tvec in zip(solved[1], solved[2]):
            rotation, _ = cv2.Rodrigues(rvec)
            depths = (rotation @ object_points.T + tvec.reshape(3, 1))[2]
            projected, _ = cv2.projectPoints(object_points, rvec, tvec, camera_matrix, distortion)
            rmse = math.sqrt(float(np.mean(np.sum((projected.reshape(-1, 2) - image_points) ** 2, axis=1))))
            candidates.append((not bool(np.all(depths > 0)), rmse, rvec, tvec, projected))
        if not candidates:
            return None
        _, rmse, rvec, tvec, projected = min(candidates, key=lambda item: (item[0], item[1]))
        return rvec, tvec, projected, rmse

    def _score(self, observations, known_indexes, width, height, reprojection_rmse):
        known = [observations[index] for index in known_indexes]
        edge = min(1.0, min(item["min_edge_px"] for item in known) / self.min_tag_edge_px)
        all_corners = np.asarray([point for item in known for point in item["corners_px"]], dtype=np.float64)
        margin = min(
            float(np.min(all_corners[:, 0])),
            float(np.min(all_corners[:, 1])),
            float(width - 1 - np.max(all_corners[:, 0])),
            float(height - 1 - np.max(all_corners[:, 1])),
        )
        border = max(0.0, min(1.0, margin / max(4.0, self.min_tag_edge_px * 0.5)))
        span_width = float(np.max(all_corners[:, 0]) - np.min(all_corners[:, 0]))
        span_height = float(np.max(all_corners[:, 1]) - np.min(all_corners[:, 1]))
        coverage = min(1.0, (span_width * span_height) / (width * height * 0.12))
        count = min(1.0, len(known) / 2.0)
        reprojection = max(0.0, min(1.0, 1.0 - reprojection_rmse / self.max_reprojection_error_px))
        return {
            "tag_size": edge,
            "image_border": border,
            "spatial_coverage": coverage,
            "known_tag_count": count,
            "reprojection": reprojection,
        }
