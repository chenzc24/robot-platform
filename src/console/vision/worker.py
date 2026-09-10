"""Bounded RTSP worker and structured logging for AprilTag localization."""

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .apriltag_localizer import AprilTagBoardLocalizer
from .apriltag_center_delta import AprilTagCenterDeltaLocalizer
from .calibration import load_board_layout, load_camera_calibration


class VisionEventLog:
    """Append compact JSON events without making vision depend on log storage."""

    def __init__(self, path):
        self.path = Path(path) if path else None
        self._lock = threading.Lock()

    def write(self, event, **fields):
        if self.path is None:
            return
        record = {
            "time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "event": str(event),
            **fields,
        }
        line = json.dumps(record, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
        except OSError:
            return


class RtspAprilTagWorker:
    """Decode a bounded-rate subset of RTSP frames in a daemon thread."""

    def __init__(self, url, timeout_seconds, detection_fps, localizer, callback, event_log=None, decoder_factory=None):
        self.url = url
        self.timeout_seconds = float(timeout_seconds)
        self.detection_fps = float(detection_fps)
        self.localizer = localizer
        self.callback = callback
        self.event_log = event_log or VisionEventLog(None)
        self.decoder_factory = decoder_factory or self._default_decoder_factory
        self._stop_event = threading.Event()
        self._thread = None
        self._last_logged_status = None
        self._last_pose_log = 0.0

    @staticmethod
    def _default_decoder_factory(url, timeout_seconds):
        import av

        return av.open(
            url,
            options={"rtsp_transport": "tcp"},
            timeout=(timeout_seconds, timeout_seconds),
        )

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return False
        if not self.url or self.timeout_seconds <= 0 or self.detection_fps <= 0:
            raise ValueError("vision_rtsp_configuration_invalid")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="console-apriltag-vision", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(self.timeout_seconds + 1.0)
        return thread is None or not thread.is_alive()

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def _run(self):
        container = None
        self.event_log.write(
            "vision_started",
            dictionary="DICT_APRILTAG_36H11",
            layout_id=self.localizer.board.layout_id,
            calibration_id=getattr(
                self.localizer, "calibration_id", self.localizer.camera.calibration_id
            ),
            camera_calibration_ready=self.localizer.camera.production_ready,
            board_layout_ready=self.localizer.board.production_ready,
            localization_method=getattr(self.localizer, "localization_method", "pose_pnp"),
            detection_fps=self.detection_fps,
        )
        try:
            container = self.decoder_factory(self.url, self.timeout_seconds)
            next_frame_at = 0.0
            for frame in container.decode(video=0):
                if self._stop_event.is_set():
                    break
                now = time.monotonic()
                if now < next_frame_at:
                    continue
                next_frame_at = now + 1.0 / self.detection_fps
                image = frame.to_ndarray(format="bgr24")
                result = self.localizer.process(image)
                self.callback(result)
                self._log_result(result, now)
        except Exception as error:
            code = self._error_code(error)
            self.event_log.write("vision_failed", error=code)
            self.callback({
                "enabled": True,
                "status": "error",
                "error": code,
                "observations": [],
                "pose_solved": False,
                "accepted": False,
                "confidence": 0.0,
                "confidence_kind": "quality_score_not_probability",
            })
        finally:
            if container is not None:
                try:
                    container.close()
                except Exception:
                    pass
            self.event_log.write("vision_stopped", requested=self._stop_event.is_set())

    def _log_result(self, result, now):
        status = result.get("status", "unknown")
        periodic_pose = (
            result.get("pose_solved") or result.get("position_solved")
        ) and now - self._last_pose_log >= 2.0
        if status == self._last_logged_status and not periodic_pose:
            return
        self._last_logged_status = status
        if periodic_pose:
            self._last_pose_log = now
        self.event_log.write(
            "localization",
            frame_sequence=result.get("frame_sequence"),
            status=status,
            accepted=bool(result.get("accepted")),
            camera_calibration_ready=result.get("camera_calibration_ready"),
            board_layout_ready=result.get("board_layout_ready"),
            rail_reference_ready=result.get("rail_reference_ready"),
            localization_method=result.get("localization_method"),
            confidence=result.get("confidence"),
            threshold=result.get("confidence_threshold"),
            detected_ids=[item.get("id") for item in result.get("observations", [])],
            used_ids=result.get("used_ids", []),
            reprojection_rmse_px=result.get("reprojection_rmse_px"),
            tvec_board_origin_in_camera_mm=result.get("tvec_board_origin_in_camera_mm"),
            T_camera_from_board=result.get("T_camera_from_board"),
            rail_position_mm=result.get("rail_position_mm"),
            tag_disagreement_mm=result.get("tag_disagreement_mm"),
            max_cross_axis_error_mm=result.get("max_cross_axis_error_mm"),
            error=result.get("error", "none"),
        )

    @staticmethod
    def _error_code(error):
        text = str(error).strip()
        if text and len(text) <= 96 and all(character.isalnum() or character in "_-.:" for character in text):
            return text
        return error.__class__.__name__


def create_vision_worker(config, callback, decoder_factory=None):
    """Build the worker only after explicit vision enablement."""
    if not config.vision.complete:
        raise ValueError("vision_configuration_incomplete")
    board = config.vision.board_layout
    camera = config.vision.camera_calibration
    if board is None or camera is None:
        board = load_board_layout(config.vision.board_layout_path)
        camera = load_camera_calibration(config.vision.camera_calibration_path)
    if board.dictionary != config.vision.dictionary:
        raise ValueError("vision_dictionary_mismatch")
    if config.localization.method == "center_delta":
        localizer = AprilTagCenterDeltaLocalizer(
            camera,
            board,
            config.localization.center_reference,
            rail_axis=config.localization.rail_axis,
            min_tag_edge_px=config.vision.min_tag_edge_px,
            min_confidence=config.vision.min_confidence,
            min_visible_tags=config.localization.min_visible_tags,
        )
    else:
        localizer = AprilTagBoardLocalizer(
            camera,
            board,
            min_tag_edge_px=config.vision.min_tag_edge_px,
            max_reprojection_error_px=config.vision.max_reprojection_error_px,
            min_confidence=config.vision.min_confidence,
        )
    return RtspAprilTagWorker(
        config.video.rtsp_url,
        config.video.connect_timeout_seconds,
        config.vision.detection_fps,
        localizer,
        callback,
        event_log=VisionEventLog(config.vision.log_path),
        decoder_factory=decoder_factory,
    )
