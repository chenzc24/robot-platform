"""L1 tests for local console runtime adapters without real endpoints."""

import json
import os
import pathlib
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "console"))

from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from ui.controller import ConsoleController
from ui.models import Environment, Lifecycle, LinkState
from ui.runtime import RuntimeCoordinator, SerializedSession, SessionFault, SessionResult, VideoDecoderWorker, VideoFrame, _arm_dispatch, _default_decoder_factory, _ensure_runtime_import_paths
from runtime_config import (
    ArmConfig,
    ChassisConfig,
    ManualChassisConfig,
    RuntimeConfig,
    RuntimeConfigError,
    VideoConfig,
    load_runtime_config,
)
from ui.views import MainWindow


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


class TwoFrameContainer(FakeContainer):
    def decode(self, video=0):
        self.video_index = video
        yield FakeFrame()
        yield FakeFrame()


class BlockingContainer:
    def __init__(self):
        self.closed = threading.Event()
        self.release = threading.Event()

    def decode(self, video=0):
        self.video_index = video
        self.release.wait()
        if False:
            yield FakeFrame()

    def close(self):
        self.closed.set()


class FailingClient:
    def __init__(self):
        self.connection = FakeConnection()
        self.status_calls = 0

    def status(self):
        self.status_calls += 1
        raise OSError("connection_closed_before_response")


class ExplicitRejection(RuntimeError):
    explicit_rejection = True

    def __init__(self, code):
        super().__init__(code)
        self.code = code


class RejectingClient:
    def __init__(self):
        self.connection = FakeConnection()

    def velocity(self):
        raise ExplicitRejection("invalid_chassis_state")


class ArmLifecycleClient:
    def __init__(self, lifecycle, code="request_in_flight"):
        self.connection = FakeConnection()
        self.lifecycle, self.code = lifecycle, code
        self.calls = []

    def status(self):
        self.calls.append("status")
        return [{"lifecycle": self.lifecycle, "payload": {"error_code": self.code}}]

    def ping(self):
        return self.status()


class OrderedClient:
    def __init__(self):
        self.connection = FakeConnection()
        self.calls = []
        self.first_started = threading.Event()
        self.release_first = threading.Event()

    def status(self):
        index = len(self.calls)
        self.calls.append(index)
        if index == 0:
            self.first_started.set()
            self.release_first.wait(1.0)
        return {"sequence": index}


class SnapshotVideoWorker(QObject):
    state_changed = Signal(str)
    frame_ready = Signal(object)
    fault_raised = Signal(object)

    def __init__(self, image, fail_write=False):
        super().__init__()
        self.last_frame = VideoFrame(image, 1, 0, 0.0, 0)
        self.saved = []
        self.fail_write = fail_write

    def start(self, _url, _timeout):
        return False

    def stop(self):
        return True

    def save_snapshot(self, destination):
        if self.fail_write:
            raise RuntimeError("snapshot_write_failed")
        self.saved.append(pathlib.Path(destination))
        pathlib.Path(destination).parent.mkdir(parents=True, exist_ok=True)
        if not self.last_frame.image.save(str(destination)):
            raise RuntimeError("snapshot_write_failed")


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

    def request_chassis_health(self):
        self.calls.append("request_chassis_health")

    def request_arm_status(self):
        self.calls.append("request_arm_status")

    def request_arm_motion(self, command, payload=None):
        self.calls.append((command, payload or {}))
        return True

    def save_snapshot(self):
        self.calls.append("save_snapshot")
        return False

    def close(self):
        self.calls.append("close")


class ManualRuntime(FakeRuntime):
    def __init__(self):
        super().__init__()
        self.manual_chassis_enabled = True
        self.config = SimpleNamespace(
            chassis=SimpleNamespace(client_id="console-l2"),
            manual_chassis=SimpleNamespace(
                health_interval_ms=500,
                velocity_hold_ms=500,
                linear_limit_mm_s=600,
                angular_limit_mrad_s=800,
            )
        )

    def request_chassis_manual(self, command, payload=None):
        self.calls.append((command, payload or {}))
        return True


class RuntimeConfigTests(unittest.TestCase):
    def test_runtime_import_paths_expose_protocol_and_console_clients(self):
        expected = {str(ROOT / "protocol"), str(ROOT / "src" / "console")}
        original = list(sys.path)
        try:
            sys.path[:] = [item for item in sys.path if item not in expected]
            _ensure_runtime_import_paths()
            self.assertTrue(expected.issubset(sys.path))
        finally:
            sys.path[:] = original

    def test_loader_accepts_secret_free_template_shape(self):
        source = {
            "schema_version": 3,
            "chassis": {"host": "", "port": 0, "client_id": "console", "connect_timeout_seconds": 3.0},
            "manual_chassis": {"enabled": False, "health_interval_ms": 250, "velocity_hold_ms": 150, "linear_limit_mm_s": 50, "angular_limit_mrad_s": 100},
            "arm": {"host": "", "port": 0, "session_id": "console", "connect_timeout_seconds": 3.0},
            "video": {"rtsp_url": "", "webrtc_url": "", "connect_timeout_seconds": 3.0, "snapshot_directory": ""},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "console.local.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            config = load_runtime_config(path)
        self.assertFalse(config.chassis.complete)
        self.assertFalse(config.manual_chassis.enabled)
        self.assertFalse(config.arm.complete)
        self.assertFalse(config.video.complete)

    def test_loader_rejects_unknown_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "console.local.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeConfigError, "unexpected"):
                load_runtime_config(path)

    def test_loader_rejects_non_boolean_manual_enable(self):
        source = {
            "schema_version": 3,
            "chassis": {"host": "", "port": 0, "client_id": "console", "connect_timeout_seconds": 3.0},
            "manual_chassis": {"enabled": "true", "health_interval_ms": 250, "velocity_hold_ms": 150, "linear_limit_mm_s": 50, "angular_limit_mrad_s": 100},
            "arm": {"host": "", "port": 0, "session_id": "console", "connect_timeout_seconds": 3.0},
            "video": {"rtsp_url": "", "webrtc_url": "", "connect_timeout_seconds": 3.0, "snapshot_directory": ""},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "console.local.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeConfigError, "manual_chassis.enabled"):
                load_runtime_config(path)

    def test_loader_rejects_health_interval_above_supported_limit(self):
        source = {
            "schema_version": 3,
            "chassis": {"host": "", "port": 0, "client_id": "console", "connect_timeout_seconds": 3.0},
            "manual_chassis": {"enabled": False, "health_interval_ms": 1001, "velocity_hold_ms": 150, "linear_limit_mm_s": 50, "angular_limit_mrad_s": 100},
            "arm": {"host": "", "port": 0, "session_id": "console", "connect_timeout_seconds": 3.0},
            "video": {"rtsp_url": "", "webrtc_url": "", "connect_timeout_seconds": 3.0, "snapshot_directory": ""},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "console.local.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeConfigError, "manual_chassis.health_interval_ms"):
                load_runtime_config(path)


class RuntimeWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication(["runtime-tests"])

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

    def test_default_video_decoder_uses_open_and_read_timeouts(self):
        calls = []
        expected = object()

        def fake_open(url, **kwargs):
            calls.append((url, kwargs))
            return expected

        with mock.patch.dict(sys.modules, {"av": SimpleNamespace(open=fake_open)}):
            actual = _default_decoder_factory("rtsp://local/stream", 2.5)

        self.assertIs(actual, expected)
        self.assertEqual(
            calls,
            [
                (
                    "rtsp://local/stream",
                    {
                        "options": {"rtsp_transport": "tcp"},
                        "timeout": (2.5, 2.5),
                    },
                )
            ],
        )

    def test_video_worker_reports_low_frame_rate_and_can_restart_after_completion(self):
        containers = [TwoFrameContainer(), FakeContainer()]
        frames = []

        def slow_adapter(_frame):
            time.sleep(0.05)
            return 1, 1, b"\x01\x02\x03"

        worker = VideoDecoderWorker(
            decoder_factory=lambda _url, _timeout: containers.pop(0),
            frame_adapter=slow_adapter,
        )
        worker.frame_ready.connect(frames.append)
        self.assertTrue(worker.start("rtsp://local/fake", 1.0))
        self.assertTrue(wait_until(lambda: len(frames) == 2))
        self.assertEqual(frames[0].fps, 0.0)
        self.assertLess(frames[1].fps, 100.0)
        self.assertTrue(wait_until(lambda: worker._thread is not None and not worker._thread.is_alive()))
        self.assertTrue(worker.start("rtsp://local/fake", 1.0))
        self.assertTrue(wait_until(lambda: len(frames) == 3))
        worker.stop()

    def test_video_worker_reports_decode_failure_and_does_not_close_blocking_decoder_cross_thread(self):
        faults = []
        states = []
        blocking = BlockingContainer()
        worker = VideoDecoderWorker(decoder_factory=lambda _url, _timeout: blocking)
        worker.fault_raised.connect(faults.append)
        worker.state_changed.connect(states.append)
        self.assertTrue(worker.start("rtsp://local/fake", 1.0))
        self.assertTrue(wait_until(lambda: "online" in states))
        self.assertFalse(worker.stop(timeout_seconds=0.05))
        self.assertFalse(blocking.closed.is_set())
        self.assertTrue(any(item.code == "video_stop_timeout" for item in faults))
        self.assertIn("degraded", states)
        blocking.release.set()
        self.assertTrue(wait_until(lambda: worker._thread is not None and not worker._thread.is_alive()))
        self.assertTrue(blocking.closed.is_set())
        self.assertTrue(wait_until(lambda: "offline" in states))

        faults.clear()
        failed = VideoDecoderWorker(decoder_factory=lambda _url, _timeout: (_ for _ in ()).throw(RuntimeError("decode failed")))
        failed.fault_raised.connect(faults.append)
        self.assertTrue(failed.start("rtsp://local/fake", 1.0))
        self.assertTrue(wait_until(lambda: bool(faults)))
        self.assertEqual(faults[-1].code, "video_decode_failed")

    def test_session_surfaces_safe_request_failure_without_retry_and_preserves_fifo(self):
        failing = FailingClient()
        results = []
        states = []
        session = SerializedSession("ESP32", lambda: failing, lambda client, command, _payload: getattr(client, command)(), {"status"}, {"velocity"})
        session.result_ready.connect(results.append)
        session.state_changed.connect(states.append)
        try:
            session.connect()
            self.assertTrue(wait_until(lambda: any(item.command == "connect" for item in results)))
            session.request("status")
            self.assertTrue(wait_until(lambda: any(item.command == "status" for item in results)))
            self.assertEqual(failing.status_calls, 1)
            self.assertEqual(results[-1].lifecycle, Lifecycle.FAULT)
            self.assertTrue(wait_until(lambda: "offline" in states))
            self.assertTrue(failing.connection.closed)

            ordered = OrderedClient()
            ordered_results = []
            second = SerializedSession("ESP32", lambda: ordered, lambda client, command, _payload: getattr(client, command)(), {"status"}, {"velocity"})
            second.result_ready.connect(ordered_results.append)
            try:
                second.connect()
                self.assertTrue(wait_until(lambda: any(item.command == "connect" for item in ordered_results)))
                second.request("status")
                second.request("status")
                self.assertTrue(ordered.first_started.wait(0.5))
                self.assertEqual(ordered.calls, [0])
                ordered.release_first.set()
                self.assertTrue(wait_until(lambda: len([item for item in ordered_results if item.command == "status"]) == 2))
                self.assertEqual(ordered.calls, [0, 1])
            finally:
                second.close()
        finally:
            session.close()

    def test_session_reports_connection_timeout_once_without_automatic_retry(self):
        attempts = []

        def timeout_factory():
            attempts.append("connect")
            raise TimeoutError("timed out")

        results = []
        session = SerializedSession("ESP32", timeout_factory, lambda *_args: None, {"status"}, {"velocity"})
        session.result_ready.connect(results.append)
        try:
            session.connect()
            self.assertTrue(wait_until(lambda: bool(results)))
            self.assertEqual(attempts, ["connect"])
            self.assertEqual(results[-1].command, "connect")
            self.assertEqual(results[-1].lifecycle, Lifecycle.FAULT)
        finally:
            session.close()

    def test_explicit_device_rejection_keeps_session_online_without_fault(self):
        client = RejectingClient()
        results = []
        states = []
        faults = []
        session = SerializedSession(
            "ESP32", lambda: client,
            lambda target, command, _payload: getattr(target, command)(),
            {"velocity"}, {"velocity"},
        )
        session.result_ready.connect(results.append)
        session.state_changed.connect(states.append)
        session.fault_raised.connect(faults.append)
        try:
            session.connect()
            self.assertTrue(wait_until(lambda: "online" in states))
            session.request("velocity")
            self.assertTrue(wait_until(lambda: any(item.command == "velocity" for item in results)))
            outcome = [item for item in results if item.command == "velocity"][-1]
            self.assertEqual(outcome.lifecycle, Lifecycle.REJECTED)
            self.assertEqual(outcome.code, "invalid_chassis_state")
            self.assertEqual(faults, [])
            self.assertFalse(client.connection.closed)
            self.assertNotIn("offline", states)
        finally:
            session.close()

    def test_arm_terminal_rejection_is_not_misreported_as_completed_status(self):
        client = ArmLifecycleClient("REJECTED")
        results, states, faults = [], [], []
        session = SerializedSession(
            "MaixCam", lambda: client, _arm_dispatch, {"status"}, {"move_joint"},
        )
        session.result_ready.connect(results.append)
        session.state_changed.connect(states.append)
        session.fault_raised.connect(faults.append)
        try:
            session.connect()
            self.assertTrue(wait_until(lambda: "online" in states))
            session.request("status")
            self.assertTrue(wait_until(lambda: any(item.command == "status" for item in results)))
            outcome = [item for item in results if item.command == "status"][-1]
            self.assertEqual(outcome.lifecycle, Lifecycle.REJECTED)
            self.assertEqual(outcome.code, "request_in_flight")
            self.assertEqual(client.calls, ["status"])
            self.assertEqual(faults, [])
            self.assertFalse(client.connection.closed)
        finally:
            session.close()

    def test_snapshot_stays_inside_injected_local_root(self):
        image = QImage(2, 1, QImage.Format.Format_RGB888)
        image.fill(0xFF336699)
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory) / "logs"
            config = RuntimeConfig(
            ChassisConfig("", 0, 1.0, "console"),
                ManualChassisConfig(False, 250, 150, 50, 100),
                ArmConfig("", 0, 1.0, "console"),
                VideoConfig("", "", 1.0, "session"),
            )
            worker = SnapshotVideoWorker(image)
            runtime = RuntimeCoordinator(config, video_worker=worker, snapshot_root=root)
            self.assertTrue(runtime.save_snapshot())
            self.assertEqual(len(worker.saved), 1)
            self.assertTrue(worker.saved[0].is_file())
            self.assertTrue(worker.saved[0].is_relative_to(root.resolve()))

            outside = RuntimeConfig(config.chassis, config.manual_chassis, config.arm, VideoConfig("", "", 1.0, "../outside"))
            rejected = RuntimeCoordinator(outside, video_worker=SnapshotVideoWorker(image), snapshot_root=root)
            faults = []
            rejected.fault_raised.connect(faults.append)
            self.assertFalse(rejected.save_snapshot())
            self.assertEqual(faults[-1].code, "snapshot_path_outside_allowed_root")

            failed = RuntimeCoordinator(config, video_worker=SnapshotVideoWorker(image, fail_write=True), snapshot_root=root)
            failed_faults = []
            failed.fault_raised.connect(failed_faults.append)
            self.assertFalse(failed.save_snapshot())
            self.assertEqual(failed_faults[-1].code, "snapshot_write_failed")

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

        runtime.result_ready.emit(SessionResult("ESP32", "status", Lifecycle.DONE, "completed", {
            "version": 3, "sequence": 2, "type": "STATE", "ttl_ms": 0,
            "payload": {
                "service_state": "safe_idle", "chassis_state": "disabled", "motion_permitted": False,
                "authenticated": True, "hold_remaining_ms": 0, "last_error": "none",
            },
        }))
        self.assertEqual(controller.state.chassis.reported_state, "disabled")
        self.assertFalse(controller.state.chassis.motion_enabled)

        runtime.arm_state_changed.emit("online")
        runtime.result_ready.emit(SessionResult("MaixCam", "status", Lifecycle.DONE, "completed", [{
            "version": 1, "kind": "lifecycle", "message_id": "console-2:done", "sequence": 2,
            "target": "arm", "name": "arm.status", "ttl_ms": 0,
            "payload": {"downstream_sequence": 7, "terminal_position": "unknown", "downstream_payload": "service_state=ready;motion_enabled=0;control_mode=production;active_sequence=0;last_error=none;terminal_position_supported=0;cancel_supported=0;feedback_valid=1;feedback_error=none;joint_deg=1,2,3,4,5,6;pose=101,202,303,1.5,2.5,3.5;pose_user=0;pose_tool=0;sample_id=1;sample_time_ms=1234"},
            "correlation_id": "console-2", "lifecycle": "DONE",
        }]))
        self.assertEqual(controller.state.arm.uart_lan1, LinkState.ONLINE)
        self.assertEqual(controller.state.arm.controller, LinkState.ONLINE)
        self.assertEqual(controller.state.arm.reported_state, "ready")

        image = QImage(1, 1, QImage.Format.Format_RGB888)
        runtime.frame_ready.emit(VideoFrame(image, 3, 0, 20.0, 0))
        self.assertEqual(controller.state.video.link, LinkState.ONLINE)
        self.assertEqual(controller.state.video.resolution, (1, 1))

    def test_hardware_manual_enable_disable_and_velocity_bounds(self):
        runtime = ManualRuntime()
        controller = ConsoleController(runtime=runtime)
        controller.set_environment(Environment.HARDWARE)
        self.assertFalse(controller.chassis_stop())
        self.assertEqual(runtime.calls, [])
        controller._replace(chassis=controller.state.chassis.__class__(
            link=LinkState.ONLINE,
            authenticated=True,
            motion_permitted=True,
            reported_state="disabled",
        ))
        self.assertTrue(controller.chassis_enable())
        self.assertEqual(runtime.calls[-1], ("enable", {}))
        controller._replace(chassis=controller.state.chassis.__class__(
            link=LinkState.ONLINE,
            authenticated=True,
            motion_permitted=True,
            motion_enabled=True,
            reported_state="enabled stopped",
        ))
        self.assertTrue(controller.chassis_velocity(600, 0, 0))
        self.assertEqual(runtime.calls[-1][0], "velocity")
        self.assertEqual(controller._velocity_refresh_timer.interval(), 100)
        before_refresh = len(runtime.calls)
        controller._velocity_refresh_tick()
        self.assertEqual(len(runtime.calls), before_refresh + 1)
        self.assertEqual(runtime.calls[-1][0], "velocity")
        self.assertFalse(controller.chassis_velocity(601, 0, 0))
        self.assertTrue(controller.chassis_stop())
        self.assertEqual(runtime.calls[-1], ("stop", {}))
        self.assertFalse(controller._velocity_refresh_timer.isActive())
        self.assertTrue(controller.chassis_disable())
        self.assertEqual(runtime.calls[-1], ("disable", {}))

    def test_health_polling_is_background_and_does_not_enable_motion(self):
        runtime = ManualRuntime()
        controller = ConsoleController(runtime=runtime)
        controller.set_environment(Environment.HARDWARE)
        controller._replace(chassis=controller.state.chassis.__class__(
            link=LinkState.ONLINE,
            authenticated=True,
            motion_permitted=True,
            reported_state="status pending",
        ))
        controller._apply_chassis_status({
            "version": 3, "sequence": 1, "type": "STATE", "ttl_ms": 0,
            "payload": {
                "service_state": "ready", "chassis_state": "disabled", "motion_permitted": True,
                "authenticated": True, "hold_remaining_ms": 0, "last_error": "none",
            },
        })
        self.assertTrue(controller._health_timer.isActive())
        self.assertEqual(controller._health_timer.interval(), 500)
        self.assertFalse(controller.can_chassis_move())
        controller._health_tick()
        self.assertEqual(runtime.calls, ["request_chassis_health"])

    def test_clean_esp32_state_clears_only_recovered_esp32_faults(self):
        controller = ConsoleController(runtime=ManualRuntime())
        controller.set_environment(Environment.HARDWARE)
        controller._raise_fault("invalid_chassis_state", "fault", "esp32", "safe request failed")
        controller._raise_fault("enable_outcome_unknown", "unknown", "esp32", "inspect device")
        controller._raise_fault("arm_route_fault", "fault", "arm", "arm fault")
        controller._apply_chassis_status({
            "version": 3, "sequence": 1, "type": "STATE", "ttl_ms": 0,
            "payload": {
                "service_state": "ready", "chassis_state": "disabled", "motion_permitted": True,
                "authenticated": True, "hold_remaining_ms": 0, "last_error": "none",
            },
        })
        self.assertNotIn("invalid_chassis_state", controller._faults)
        self.assertIn("enable_outcome_unknown", controller._faults)
        self.assertIn("arm_route_fault", controller._faults)

    def test_hardware_enable_view_uses_authenticated_session(self):
        runtime = ManualRuntime()
        controller = ConsoleController(runtime=runtime)
        controller.set_environment(Environment.HARDWARE)
        controller._replace(chassis=controller.state.chassis.__class__(
            link=LinkState.ONLINE,
            authenticated=True,
            motion_permitted=True,
            motion_enabled=False,
            reported_state="disabled",
        ))
        window = MainWindow(controller)
        try:
            self.assertTrue(window.chassis_enable_button.isEnabled())
            self.assertEqual(window.linear_slider.maximum(), 600)
            self.assertEqual(window.angular_slider.maximum(), 800)
            self.assertEqual(window.chassis_vector_label.text(), "Cmd 0 / 0 / 0")
        finally:
            window.close()

    def test_hardware_arm_view_shows_controls_but_disables_them_outside_yolo(self):
        runtime = ManualRuntime()
        controller = ConsoleController(runtime=runtime)
        controller.set_environment(Environment.HARDWARE)
        controller._replace(arm=controller.state.arm.__class__(
            gateway=LinkState.ONLINE,
            uart_lan1=LinkState.ONLINE,
            controller=LinkState.ONLINE,
            task=Lifecycle.IDLE,
            reported_state="ready",
            motion_permitted=False,
            last_status_age_ms=0,
        ))
        window = MainWindow(controller)
        try:
            self.assertFalse(window.arm_tabs.isHidden())
            self.assertFalse(window.joint_execute_button.isEnabled())
            self.assertIn("not in YOLO", window.arm_runtime_detail.text())
        finally:
            window.close()

    def test_hardware_yolo_joint_jog_is_repeatable_and_independent_of_esp32(self):
        runtime = ManualRuntime()
        controller = ConsoleController(runtime=runtime)
        controller.set_environment(Environment.HARDWARE)
        controller._replace(
            arm=controller.state.arm.__class__(
                gateway=LinkState.ONLINE, uart_lan1=LinkState.ONLINE,
                controller=LinkState.ONLINE, task=Lifecycle.IDLE,
                reported_state="ready", motion_permitted=True, control_mode="yolo",
            ),
        )
        window = MainWindow(controller)
        try:
            self.assertTrue(window.joint_jog_buttons[1].isEnabled())
            self.assertEqual(window.joint_jog_step.value(), 2.0)
            self.assertTrue(controller.jog_arm_joint(0, 2.0))
            self.assertEqual(runtime.calls[-1], ("jog_joint", {"joint_delta_deg": [2.0, 0.0, 0.0, 0.0, 0.0, 0.0], "accel_pct": 5, "speed_pct": 5}))
            responses = [
                {"lifecycle": "RECEIVED", "payload": {}},
                {"lifecycle": "ACCEPTED", "payload": {"downstream_sequence": 8}},
                {"lifecycle": "RUNNING", "payload": {"downstream_sequence": 8}},
                {"lifecycle": "DONE", "payload": {"downstream_sequence": 8}},
            ]
            runtime.result_ready.emit(SessionResult("MaixCam", "jog_joint", Lifecycle.DONE, "completed", responses))
            self.assertEqual(controller.state.arm.task, Lifecycle.IDLE)
            self.assertIn("request_arm_status", runtime.calls)
            self.assertEqual([event.lifecycle for event in controller.events[:4]], [Lifecycle.DONE, Lifecycle.RUNNING, Lifecycle.ACCEPTED, Lifecycle.RECEIVED])
            controller._replace(arm=controller.state.arm.__class__(
                gateway=LinkState.ONLINE, uart_lan1=LinkState.ONLINE,
                controller=LinkState.ONLINE, task=Lifecycle.IDLE,
                reported_state="ready", motion_permitted=True, control_mode="yolo",
            ))
            self.assertTrue(controller.jog_arm_joint(0, -2.0))
        finally:
            window.close()

    def test_hardware_yolo_jog_does_not_depend_on_chassis_or_ui_fault_panel(self):
        runtime = ManualRuntime()
        controller = ConsoleController(runtime=runtime)
        controller.set_environment(Environment.HARDWARE)
        controller._replace(arm=controller.state.arm.__class__(
            gateway=LinkState.ONLINE, uart_lan1=LinkState.ONLINE,
            controller=LinkState.ONLINE, task=Lifecycle.IDLE,
            reported_state="ready", motion_permitted=True, control_mode="yolo",
        ))
        controller._raise_fault("esp32_offline", "fault", "esp32", "not part of arm debug")
        self.assertTrue(controller.can_arm_move())
        controller._raise_fault("arm_route_fault", "fault", "arm", "arm route failed")
        self.assertTrue(controller.can_arm_move())

    def test_live_event_log_records_only_sanitized_event_and_fault_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "console-events.log"
            controller = ConsoleController(event_log_path=path)
            controller._record(
                "ESP32", "status", Lifecycle.DONE, "completed",
                detail="credential=must-not-appear",
            )
            controller._raise_fault(
                "control_not_owned", "fault", "esp32", "safe request failed",
            )
            content = path.read_text(encoding="utf-8")
        self.assertIn("EVENT", content)
        self.assertIn("command=status", content)
        self.assertIn("result=completed", content)
        self.assertIn("FAULT", content)
        self.assertIn("code=control_not_owned", content)
        self.assertNotIn("credential=must-not-appear", content)

    def test_hardware_ui_binds_decoded_frame_and_retains_invalid_status_fault(self):
        runtime = FakeRuntime()
        controller = ConsoleController(runtime=runtime)
        window = MainWindow(controller)
        try:
            controller.set_environment(Environment.HARDWARE)
            runtime.frame_ready.emit(VideoFrame(QImage(3, 2, QImage.Format.Format_RGB888), 9, 0, 18.0, 4))
            self.assertEqual((window.video_canvas._image.width(), window.video_canvas._image.height()), (3, 2))
            runtime.result_ready.emit(SessionResult("ESP32", "status", Lifecycle.DONE, "completed", {"type": "STATE", "payload": {}}))
            self.assertTrue(any(item.code == "invalid_chassis_status_response" for item in controller.state.faults))
            controller.recheck()
            self.assertTrue(any(item.code == "invalid_chassis_status_response" for item in controller.state.faults))
            self.assertFalse(window.chassis_enable_button.isEnabled())
            self.assertFalse(window.joint_execute_button.isEnabled())
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
