"""L1 tests for local console runtime adapters without real endpoints."""

import json
import pathlib
import sys
import tempfile
import time
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "console"))

from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtGui import QImage

from ui.controller import ConsoleController
from ui.models import Environment, Lifecycle, LinkState
from ui.runtime import SerializedSession, SessionResult, VideoDecoderWorker, VideoFrame
from ui.runtime_config import (
    ArmConfig,
    ChassisConfig,
    RuntimeConfig,
    RuntimeConfigError,
    VideoConfig,
    load_runtime_config,
)


def wait_until(predicate, timeout_seconds=1.5):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    QCoreApplication.processEvents()
    return predicate()


class FakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeChassisClient:
    def __init__(self):
        self.connection = FakeConnection()
        self.status_calls = 0
        self.velocity_calls = 0

    def status(self):
        self.status_calls += 1
        return {"type": "STATE", "payload": {"service": "safe_idle"}}

    def velocity(self, *_args):
        self.velocity_calls += 1
        return {"type": "DONE"}


class FakeFrame:
    pass


class FakeContainer:
    def __init__(self):
        self.closed = False

    def decode(self, video=0):
        self.video_index = video
        yield FakeFrame()

    def close(self):
        self.closed = True


class FakeRuntime(QObject):
    chassis_state_changed = Signal(str)
    arm_state_changed = Signal(str)
    video_state_changed = Signal(str)
    result_ready = Signal(object)
    fault_raised = Signal(object)
    frame_ready = Signal(object)

    def __init__(self):
        super().__init__()
        self.calls = []

    def connect_chassis(self):
        self.calls.append("connect_chassis")
        return True

    def connect_arm(self):
        self.calls.append("connect_arm")
        return True

    def connect_video(self):
        self.calls.append("connect_video")
        return True

    def disconnect_chassis(self):
        self.calls.append("disconnect_chassis")

    def disconnect_arm(self):
        self.calls.append("disconnect_arm")

    def disconnect_video(self):
        self.calls.append("disconnect_video")

    def request_chassis_status(self):
        self.calls.append("request_chassis_status")

    def request_arm_status(self):
        self.calls.append("request_arm_status")

    def save_snapshot(self):
        self.calls.append("save_snapshot")
        return False

    def close(self):
        self.calls.append("close")


class RuntimeConfigTests(unittest.TestCase):
    def test_loader_accepts_secret_free_template_shape(self):
        source = {
            "schema_version": 1,
            "chassis": {"host": "", "port": 0, "client_id": "console", "credential_env": "ROBOT_CHASSIS_CREDENTIAL", "connect_timeout_seconds": 3.0},
            "arm": {"host": "", "port": 0, "session_id": "console", "connect_timeout_seconds": 3.0},
            "video": {"rtsp_url": "", "connect_timeout_seconds": 3.0, "snapshot_directory": ""},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "console.local.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            config = load_runtime_config(path)
        self.assertFalse(config.chassis.complete)
        self.assertFalse(config.arm.complete)
        self.assertFalse(config.video.complete)

    def test_loader_rejects_unknown_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "console.local.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeConfigError, "unexpected"):
                load_runtime_config(path)


class RuntimeWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QCoreApplication.instance() or QCoreApplication(["runtime-tests"])

    def test_session_serializes_safe_requests_and_rejects_motion_before_client_call(self):
        client = FakeChassisClient()
        results = []
        states = []
        session = SerializedSession(
            "ESP32",
            lambda: client,
            lambda target, command, payload: getattr(target, command)(**payload),
            {"status"},
            {"velocity"},
        )
        session.result_ready.connect(results.append)
        session.state_changed.connect(states.append)
        try:
            session.connect()
            self.assertTrue(wait_until(lambda: "online" in states))
            session.request("status")
            session.request("velocity", {"vx_mm_s": 1})
            self.assertTrue(wait_until(lambda: len(results) >= 3))
            self.assertEqual(client.status_calls, 1)
            self.assertEqual(client.velocity_calls, 0)
            self.assertEqual(results[-2].lifecycle, Lifecycle.DONE)
            self.assertEqual(results[-1].lifecycle, Lifecycle.REJECTED)
            self.assertEqual(results[-1].code, "motion_not_admitted")
            self.assertTrue(all(result.command != "retry" for result in results))
        finally:
            session.close()
        self.assertTrue(client.connection.closed)

    def test_video_worker_copies_rgb_frame_without_pyav_or_network(self):
        container = FakeContainer()
        frames = []
        states = []
        worker = VideoDecoderWorker(
            decoder_factory=lambda _url, _timeout: container,
            frame_adapter=lambda _frame: (2, 1, b"\x01\x02\x03\x04\x05\x06"),
        )
        worker.frame_ready.connect(frames.append)
        worker.state_changed.connect(states.append)
        self.assertTrue(worker.start("rtsp://simulator/stream", 1.0))
        self.assertTrue(wait_until(lambda: len(frames) == 1))
        frame = frames[0]
        self.assertEqual(frame.frame_id, 1)
        self.assertEqual((frame.image.width(), frame.image.height()), (2, 1))
        self.assertIn("online", states)
        worker.stop()
        self.assertTrue(container.closed)

    def test_hardware_controller_uses_status_only_runtime_and_keeps_motion_locked(self):
        runtime = FakeRuntime()
        controller = ConsoleController(runtime=runtime)
        controller.set_environment(Environment.HARDWARE)
        self.assertTrue(controller.connect_chassis())
        self.assertEqual(runtime.calls[-1], "connect_chassis")

        runtime.chassis_state_changed.emit("online")
        self.assertIn("request_chassis_status", runtime.calls)
        self.assertEqual(controller.state.chassis.link, LinkState.ONLINE)
        self.assertFalse(controller.can_chassis_move())
        self.assertFalse(controller.chassis_velocity(1, 0, 0))

        runtime.result_ready.emit(SessionResult("ESP32", "status", Lifecycle.DONE, "completed"))
        self.assertEqual(controller.state.chassis.reported_state, "status received")

        image = QImage(1, 1, QImage.Format.Format_RGB888)
        runtime.frame_ready.emit(VideoFrame(image, 3, 0, 20.0, 0))
        self.assertEqual(controller.state.video.link, LinkState.ONLINE)
        self.assertEqual(controller.state.video.resolution, (1, 1))


if __name__ == "__main__":
    unittest.main()
