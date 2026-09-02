"""Non-blocking, default-deny runtime adapters for the desktop console."""

import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from runtime_core import (
    MOTION_ARM_COMMANDS,
    MOTION_CHASSIS_COMMANDS,
    SAFE_ARM_COMMANDS,
    SAFE_CHASSIS_COMMANDS,
    ArmLifecycleRejection,
    SessionFault,
    SessionResult,
    close_client as _close_client,
    default_arm_factory as _default_arm_factory,
    default_chassis_factory as _default_chassis_factory,
    dispatch_arm as _arm_dispatch,
    dispatch_chassis as _chassis_dispatch,
    ensure_runtime_import_paths as _ensure_runtime_import_paths,
    source_root as _source_root,
)

from .models import Lifecycle
from runtime_config import RuntimeConfig


@dataclass(frozen=True)
class VideoFrame:
    image: QImage
    frame_id: int
    timestamp_ms: int
    fps: float
    decode_latency_ms: int


class SerializedSession(QObject):
    """Own exactly one blocking client in one background worker thread.

    Operations are FIFO. Explicit device rejection keeps the healthy connection;
    a transport failure during a state-changing request emits `UNKNOWN` and
    disconnects. State-changing requests are never retried automatically.
    """

    state_changed = Signal(str)
    result_ready = Signal(object)
    fault_raised = Signal(object)

    def __init__(self, target, factory, dispatcher, safe_commands, motion_commands, parent=None):
        super().__init__(parent)
        self.target = target
        self._factory = factory
        self._dispatcher = dispatcher
        self._safe_commands = set(safe_commands)
        self._motion_commands = set(motion_commands)
        self._operations = queue.Queue()
        self._client = None
        self._thread = None
        self._thread_lock = threading.Lock()

    def _start_if_needed(self):
        with self._thread_lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="console-%s-session" % self.target.lower(), daemon=True)
                self._thread.start()

    def connect(self):
        self._start_if_needed()
        self._operations.put(("connect", None, None))

    def request(self, command, payload=None):
        self._start_if_needed()
        operation = ("request", command, payload or {})
        if command in {"velocity", "ping"}:
            self._replace_pending(command, operation)
        elif command in {"stop", "disable"}:
            self._prioritize_safe_output(operation)
        else:
            self._operations.put(operation)

    def _replace_pending(self, command, operation):
        """Keep only the newest periodic request; never build a motion backlog."""
        with self._operations.mutex:
            retained = [
                item for item in self._operations.queue
                if not (item[0] == "request" and item[1] == command)
            ]
            self._operations.queue.clear()
            self._operations.queue.extend(retained)
            self._operations.queue.append(operation)
            self._operations.not_empty.notify()

    def _prioritize_safe_output(self, operation):
        """Drop stale periodic requests and schedule stop-like output next."""
        with self._operations.mutex:
            retained = [
                item for item in self._operations.queue
                if not (item[0] == "request" and item[1] in {"velocity", "ping"})
            ]
            self._operations.queue.clear()
            self._operations.queue.extend(retained)
            self._operations.queue.appendleft(operation)
            self._operations.not_empty.notify()

    def disconnect(self):
        self._start_if_needed()
        self._operations.put(("disconnect", None, None))

    def close(self, timeout_seconds=1.0):
        self._start_if_needed()
        self._operations.put(("shutdown", None, None))
        thread = self._thread
        if thread is not None:
            thread.join(timeout_seconds)

    def _emit_result(self, command, lifecycle, code, payload=None):
        self.result_ready.emit(SessionResult(self.target, command, lifecycle, code, payload))

    def _emit_fault(self, code, detail, state_changing):
        self.fault_raised.emit(SessionFault(self.target, code, detail, state_changing))

    def _run(self):
        while True:
            operation, command, payload = self._operations.get()
            if operation == "shutdown":
                self._disconnect_internal()
                return
            if operation == "disconnect":
                self._disconnect_internal()
                self._emit_result("disconnect", Lifecycle.DONE, "disconnected")
                continue
            if operation == "connect":
                self._connect_internal()
                continue
            self._request_internal(command, payload)

    def _connect_internal(self):
        self._disconnect_internal(emit_state=False)
        self.state_changed.emit("connecting")
        try:
            self._client = self._factory()
        except Exception as error:
            code = getattr(error, "code", None) or str(error) or "connection_failed"
            self.state_changed.emit("offline")
            self._emit_result("connect", Lifecycle.FAULT, code)
            self._emit_fault(code, "connection failed", False)
            return
        self.state_changed.emit("online")
        self._emit_result("connect", Lifecycle.DONE, "connected")

    def _disconnect_internal(self, emit_state=True):
        client, self._client = self._client, None
        if client is not None:
            try:
                _close_client(client)
            except Exception:
                pass
        if emit_state:
            self.state_changed.emit("offline")

    def _request_internal(self, command, payload):
        if command not in self._safe_commands:
            state_changing = command in self._motion_commands
            code = "motion_not_admitted" if state_changing else "unsupported_command"
            self._emit_result(command, Lifecycle.REJECTED, code)
            return
        if self._client is None:
            self._emit_result(command, Lifecycle.REJECTED, "not_connected")
            return
        try:
            result = self._dispatcher(self._client, command, payload)
        except Exception as error:
            code = getattr(error, "code", None) or "request_failed"
            if getattr(error, "explicit_rejection", False):
                self._emit_result(command, Lifecycle.REJECTED, code)
                return
            state_changing = command in self._motion_commands
            self._disconnect_internal()
            lifecycle = Lifecycle.UNKNOWN if state_changing else Lifecycle.FAULT
            detail = "state-changing request outcome unknown" if state_changing else "request failed"
            self._emit_result(command, lifecycle, code)
            self._emit_fault(code, detail, state_changing)
            return
        self._emit_result(command, Lifecycle.DONE, "completed", result)


def _default_frame_adapter(frame):
    pixels = frame.to_ndarray(format="rgb24")
    height, width, channels = pixels.shape
    if channels != 3:
        raise ValueError("unexpected_frame_channels")
    return width, height, bytes(pixels)


def _default_decoder_factory(url, timeout_seconds):
    import av

    return av.open(
        url,
        options={"rtsp_transport": "tcp"},
        timeout=(timeout_seconds, timeout_seconds),
    )


class VideoDecoderWorker(QObject):
    """Decode local RTSP frames in a dedicated thread and copy pixels for Qt."""

    state_changed = Signal(str)
    frame_ready = Signal(object)
    fault_raised = Signal(object)

    def __init__(self, decoder_factory=_default_decoder_factory, frame_adapter=_default_frame_adapter, parent=None):
        super().__init__(parent)
        self._decoder_factory = decoder_factory
        self._frame_adapter = frame_adapter
        self._stop_event = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self._container = None
        self.last_frame = None

    def start(self, url, timeout_seconds):
        if not isinstance(url, str) or not url.strip() or timeout_seconds <= 0:
            self.fault_raised.emit(SessionFault("Video", "video_configuration_incomplete", "RTSP URL or timeout is invalid", False))
            return False
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, args=(url.strip(), timeout_seconds), name="console-video-decoder", daemon=True)
            self._thread.start()
        return True

    def stop(self, timeout_seconds=1.0):
        """Request decoder shutdown without closing a PyAV container cross-thread."""
        self._stop_event.set()
        with self._lock:
            thread = self._thread
        if thread is not None:
            thread.join(timeout_seconds)
            if thread.is_alive():
                self.fault_raised.emit(SessionFault("Video", "video_stop_timeout", "Video decoder did not stop before timeout", False))
                self.state_changed.emit("degraded")
                return False
        self.state_changed.emit("offline")
        return True

    def save_snapshot(self, destination):
        image = self.last_frame.image if self.last_frame is not None else None
        if image is None or image.isNull():
            raise RuntimeError("snapshot_unavailable")
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not image.save(str(target)):
            raise RuntimeError("snapshot_write_failed")

    def _run(self, url, timeout_seconds):
        self.state_changed.emit("connecting")
        started = time.monotonic()
        try:
            container = self._decoder_factory(url, timeout_seconds)
            with self._lock:
                self._container = container
            self.state_changed.emit("online")
            frame_id = 0
            last_timestamp = None
            for frame in container.decode(video=0):
                if self._stop_event.is_set():
                    break
                frame_id += 1
                width, height, pixels = self._frame_adapter(frame)
                image = QImage(pixels, width, height, width * 3, QImage.Format.Format_RGB888).copy()
                now = time.monotonic()
                fps = 0.0 if last_timestamp is None else 1.0 / max(now - last_timestamp, 0.000001)
                last_timestamp = now
                decoded = VideoFrame(
                    image=image,
                    frame_id=frame_id,
                    timestamp_ms=int((now - started) * 1_000),
                    fps=fps,
                    decode_latency_ms=0,
                )
                self.last_frame = decoded
                self.frame_ready.emit(decoded)
        except Exception as error:
            if not self._stop_event.is_set():
                code = getattr(error, "code", None) or "video_decode_failed"
                self.fault_raised.emit(SessionFault("Video", code, "video decoder stopped", False))
        finally:
            with self._lock:
                container, self._container = self._container, None
            close = getattr(container, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
            self.state_changed.emit("offline")


class RuntimeCoordinator(QObject):
    """Compose independent chassis, arm, and video workers without cross-routing."""

    chassis_state_changed = Signal(str)
    arm_state_changed = Signal(str)
    video_state_changed = Signal(str)
    result_ready = Signal(object)
    fault_raised = Signal(object)
    frame_ready = Signal(object)

    def __init__(
        self,
        config,
        chassis_factory=None,
        arm_factory=None,
        video_worker=None,
        snapshot_root=None,
        parent=None,
    ):
        super().__init__(parent)
        if not isinstance(config, RuntimeConfig):
            raise TypeError("config must be RuntimeConfig")
        self.config = config
        self._snapshot_root = Path(snapshot_root or (_source_root() / "logs")).resolve()
        self.chassis = SerializedSession(
            "ESP32",
            chassis_factory or (lambda: _default_chassis_factory(config.chassis)),
            _chassis_dispatch,
            SAFE_CHASSIS_COMMANDS | (MOTION_CHASSIS_COMMANDS if config.manual_chassis.enabled else set()),
            MOTION_CHASSIS_COMMANDS,
            self,
        )
        self.arm = SerializedSession(
            "MaixCam",
            arm_factory or (lambda: _default_arm_factory(config.arm)),
            _arm_dispatch,
            SAFE_ARM_COMMANDS | MOTION_ARM_COMMANDS,
            MOTION_ARM_COMMANDS,
            self,
        )
        self.video = video_worker or VideoDecoderWorker(parent=self)
        self.chassis.state_changed.connect(self.chassis_state_changed)
        self.arm.state_changed.connect(self.arm_state_changed)
        self.video.state_changed.connect(self.video_state_changed)
        self.chassis.result_ready.connect(self.result_ready)
        self.arm.result_ready.connect(self.result_ready)
        self.chassis.fault_raised.connect(self.fault_raised)
        self.arm.fault_raised.connect(self.fault_raised)
        self.video.fault_raised.connect(self.fault_raised)
        self.video.frame_ready.connect(self.frame_ready)

    def connect_chassis(self):
        if not self.config.chassis.complete:
            self.fault_raised.emit(SessionFault("ESP32", "chassis_configuration_incomplete", "Chassis host or port is unavailable", False))
            return False
        self.chassis.connect()
        return True

    def connect_arm(self):
        if not self.config.arm.complete:
            self.fault_raised.emit(SessionFault("MaixCam", "arm_configuration_incomplete", "Arm gateway host or port is unavailable", False))
            return False
        self.arm.connect()
        return True

    def connect_video(self):
        if not self.config.video.complete:
            self.fault_raised.emit(SessionFault("Video", "video_configuration_incomplete", "RTSP URL is unavailable", False))
            return False
        return self.video.start(self.config.video.rtsp_url, self.config.video.connect_timeout_seconds)

    def disconnect_chassis(self):
        self.chassis.disconnect()

    def disconnect_arm(self):
        self.arm.disconnect()

    def disconnect_video(self):
        self.video.stop()

    def save_snapshot(self):
        directory = self.config.video.snapshot_directory
        if not directory:
            self.fault_raised.emit(SessionFault("Video", "snapshot_directory_unavailable", "Snapshot directory is not configured", False))
            return False
        requested_directory = Path(directory)
        destination_directory = (self._snapshot_root / requested_directory).resolve() if not requested_directory.is_absolute() else requested_directory.resolve()
        try:
            destination_directory.relative_to(self._snapshot_root)
        except ValueError:
            self.fault_raised.emit(SessionFault("Video", "snapshot_path_outside_allowed_root", "Snapshot path is outside the allowed local root", False))
            return False
        destination = destination_directory / ("maixcam-%d.png" % time.time_ns())
        try:
            self.video.save_snapshot(destination)
        except Exception as error:
            code = getattr(error, "code", None) or str(error) or "snapshot_failed"
            self.fault_raised.emit(SessionFault("Video", code, "Snapshot could not be written", False))
            return False
        self.result_ready.emit(SessionResult("Video", "snapshot", Lifecycle.DONE, "saved", str(destination)))
        return True

    def request_chassis_status(self):
        self.chassis.request("status")

    def request_chassis_health(self):
        self.chassis.request("ping")

    @property
    def manual_chassis_enabled(self):
        return self.config.manual_chassis.enabled

    def request_chassis_manual(self, command, payload=None):
        if command not in MOTION_CHASSIS_COMMANDS:
            raise ValueError("unsupported_manual_chassis_command")
        if not self.manual_chassis_enabled:
            self.result_ready.emit(SessionResult("ESP32", command, Lifecycle.REJECTED, "motion_not_admitted"))
            return False
        self.chassis.request(command, payload)
        return True

    def request_arm_status(self):
        self.arm.request("status")

    def request_arm_motion(self, command, payload=None):
        if command not in MOTION_ARM_COMMANDS:
            raise ValueError("unsupported_arm_motion_command")
        self.arm.request(command, payload)
        return True

    def close(self):
        self.chassis.close()
        self.arm.close()
        self.video.stop()
