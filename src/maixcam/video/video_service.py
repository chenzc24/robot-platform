"""Injectable MaixCam H.264 RTSP service with guarded resource ownership."""

from maix_runtime_status import RuntimeStatus
from resource_guard import ResourceRegistry


DEFAULT_PORT = 8554
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
DEFAULT_FPS = 20
DEFAULT_BITRATE = 2_000_000
CAMERA_RESOURCE = "camera"
VIDEO_OWNER = "rtsp_video_service"


class VideoServiceStateError(RuntimeError):
    """Raised when a lifecycle operation is invalid for the current state."""


class VideoSettings:
    """Validated immutable settings for one RTSP service instance."""

    def __init__(
        self,
        port=DEFAULT_PORT,
        width=DEFAULT_WIDTH,
        height=DEFAULT_HEIGHT,
        fps=DEFAULT_FPS,
        bitrate=DEFAULT_BITRATE,
    ):
        self.port = int(port)
        self.width = int(width)
        self.height = int(height)
        self.fps = int(fps)
        self.bitrate = int(bitrate)
        self.validate()

    def validate(self):
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be positive")
        if not 1 <= self.fps <= 60:
            raise ValueError("fps must be between 1 and 60")
        if self.bitrate <= 0:
            raise ValueError("bitrate must be positive")

    def detail(self):
        return {
            "codec": "h264",
            "port": self.port,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "bitrate": self.bitrate,
        }


class MaixRtspBackend:
    """Thin adapter around MaixPy camera and RTSP APIs."""

    def __init__(self, settings):
        from maix import camera, comm, err, image, rtsp

        self._err = err
        self._listener_removed = comm.rm_default_comm_listener()
        self._camera = camera.Camera(
            settings.width,
            settings.height,
            image.Format.FMT_YVU420SP,
        )
        self._server = rtsp.Rtsp(
            port=settings.port,
            fps=settings.fps,
            stream_type=rtsp.RtspStreamType.RTSP_STREAM_H264,
            bitrate=settings.bitrate,
        )
        self._server.bind_camera(self._camera)

    def start(self):
        result = self._server.start()
        if result != self._err.Err.ERR_NONE:
            raise RuntimeError("RTSP backend failed to start: %s" % result)
        return {
            "url": self._server.get_url(),
            "default_uart_listener_removed": self._listener_removed,
        }

    def stop(self):
        self._server.stop()


class RtspVideoService:
    """Own the camera and expose deterministic start, stop, and fault states."""

    def __init__(
        self,
        settings=None,
        backend_factory=None,
        resources=None,
        status=None,
    ):
        self.settings = settings or VideoSettings()
        self._backend_factory = backend_factory or MaixRtspBackend
        self.resources = resources or ResourceRegistry()
        self.status = status or RuntimeStatus("maixcam", "video")
        self._backend = None
        self._owns_camera = False

    def start(self):
        if self.status.state in ("starting", "running", "stopping"):
            raise VideoServiceStateError(
                "cannot start video while state is %s" % self.status.state
            )
        self.status.transition(
            "starting",
            event="rtsp_starting",
            detail=self.settings.detail(),
        )
        try:
            self.resources.acquire(CAMERA_RESOURCE, VIDEO_OWNER)
            self._owns_camera = True
            self._backend = self._backend_factory(self.settings)
            backend_detail = self._backend.start() or {}
            detail = self.settings.detail()
            detail.update(backend_detail)
            return self.status.transition(
                "running",
                event="rtsp_started",
                detail=detail,
            )
        except Exception as error:
            if self._backend is not None:
                try:
                    self._backend.stop()
                except Exception:
                    pass
            self._backend = None
            if self._owns_camera:
                self.resources.release(CAMERA_RESOURCE, VIDEO_OWNER)
                self._owns_camera = False
            self.status.transition(
                "fault",
                event="rtsp_error",
                error_code="video_start_failed",
                detail={"error_type": type(error).__name__},
            )
            raise

    def stop(self):
        if self.status.state in ("idle", "stopped"):
            return self.status.snapshot("rtsp_status")
        self.status.transition("stopping", event="rtsp_stopping")
        stop_error = None
        try:
            if self._backend is not None:
                self._backend.stop()
        except Exception as error:
            stop_error = error
        finally:
            self._backend = None
            if self._owns_camera:
                self.resources.release(CAMERA_RESOURCE, VIDEO_OWNER)
                self._owns_camera = False

        if stop_error is not None:
            self.status.transition(
                "fault",
                event="rtsp_error",
                error_code="video_stop_failed",
                detail={"error_type": type(stop_error).__name__},
            )
            raise stop_error
        return self.status.transition("stopped", event="rtsp_stopped")

    def health_snapshot(self):
        payload = self.status.snapshot("rtsp_status")
        payload["detail"] = dict(payload["detail"])
        payload["detail"]["resources"] = self.resources.snapshot()
        return payload
