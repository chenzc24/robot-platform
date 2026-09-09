"""Lifecycle, ownership, and rollback tests for the MaixCam video service."""

import pathlib
import sys
import unittest


VIDEO_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "maixcam" / "video"
sys.path.insert(0, str(VIDEO_DIR))

from maix_runtime_status import RuntimeStatus
from resource_guard import (
    ResourceBusyError,
    ResourceOwnershipError,
    ResourceRegistry,
)
from video_service import MaixRtspBackend, RtspVideoService, VideoSettings


class FakeBackend:
    instances = []
    fail_start = False
    fail_stop = False

    def __init__(self, settings):
        self.settings = settings
        self.started = False
        self.stopped = False
        type(self).instances.append(self)

    def start(self):
        if self.fail_start:
            raise OSError("injected start failure")
        self.started = True
        return {"url": "rtsp://test.invalid/live"}

    def stop(self):
        self.stopped = True
        if self.fail_stop:
            raise OSError("injected stop failure")


def make_status():
    return RuntimeStatus(
        "maixcam",
        "video",
        clock_ms=lambda: 1_000,
        output=lambda _line: None,
    )


class ResourceRegistryTests(unittest.TestCase):
    def test_resource_has_one_explicit_owner(self):
        resources = ResourceRegistry()
        resources.acquire("camera", "video")
        with self.assertRaises(ResourceBusyError):
            resources.acquire("camera", "vision")
        with self.assertRaises(ResourceOwnershipError):
            resources.release("camera", "vision")
        resources.release("camera", "video")
        self.assertIsNone(resources.owner_of("camera"))


class VideoServiceLifecycleTests(unittest.TestCase):
    def setUp(self):
        FakeBackend.instances = []
        FakeBackend.fail_start = False
        FakeBackend.fail_stop = False
        self.resources = ResourceRegistry()
        self.service = RtspVideoService(
            settings=VideoSettings(),
            backend_factory=FakeBackend,
            resources=self.resources,
            status=make_status(),
        )

    def test_start_and_stop_report_states_and_release_camera(self):
        started = self.service.start()
        self.assertEqual(started["state"], "running")
        self.assertEqual(started["event"], "rtsp_started")
        self.assertEqual(self.resources.owner_of("camera"), "rtsp_video_service")
        health = self.service.health_snapshot()
        self.assertEqual(health["detail"]["resources"]["camera"], "rtsp_video_service")
        stopped = self.service.stop()
        self.assertEqual(stopped["state"], "stopped")
        self.assertIsNone(self.resources.owner_of("camera"))

    def test_start_failure_stops_backend_and_releases_camera(self):
        FakeBackend.fail_start = True
        with self.assertRaises(OSError):
            self.service.start()
        self.assertTrue(FakeBackend.instances[-1].stopped)
        self.assertEqual(self.service.status.state, "fault")
        self.assertEqual(self.service.status.error_code, "video_start_failed")
        self.assertIsNone(self.resources.owner_of("camera"))

    def test_stop_failure_releases_camera_and_reports_fault(self):
        self.service.start()
        FakeBackend.fail_stop = True
        with self.assertRaises(OSError):
            self.service.stop()
        self.assertEqual(self.service.status.state, "fault")
        self.assertEqual(self.service.status.error_code, "video_stop_failed")
        self.assertIsNone(self.resources.owner_of("camera"))

    def test_second_service_cannot_steal_camera(self):
        self.service.start()
        second = RtspVideoService(
            backend_factory=FakeBackend,
            resources=self.resources,
            status=make_status(),
        )
        with self.assertRaises(ResourceBusyError):
            second.start()
        self.assertEqual(self.resources.owner_of("camera"), "rtsp_video_service")

    def test_invalid_settings_are_rejected_before_backend_import(self):
        with self.assertRaises(ValueError):
            VideoSettings(fps=0)
        with self.assertRaises(ValueError):
            VideoSettings(port=70_000)


class MaixBackendListenerTests(unittest.TestCase):
    def test_headless_backend_removes_key_exit_before_camera_initialization(self):
        events = []

        class FakeKey:
            @staticmethod
            def rm_default_listener():
                events.append("key_listener_removed")

        class FakeComm:
            @staticmethod
            def rm_default_comm_listener():
                events.append("uart_listener_removed")
                return True

        class FakeCameraModule:
            @staticmethod
            def Camera(*_args):
                events.append("camera_created")
                return object()

        class FakeImage:
            class Format:
                FMT_YVU420SP = object()

        class FakeRtspInstance:
            def bind_camera(self, _camera):
                events.append("camera_bound")

        class FakeRtsp:
            class RtspStreamType:
                RTSP_STREAM_H264 = object()

            @staticmethod
            def Rtsp(**_kwargs):
                return FakeRtspInstance()

        class FakeErr:
            class Err:
                ERR_NONE = 0

        fake_maix = type("FakeMaix", (), {
            "camera": FakeCameraModule,
            "comm": FakeComm,
            "err": FakeErr,
            "image": FakeImage,
            "key": FakeKey,
            "rtsp": FakeRtsp,
        })
        original = sys.modules.get("maix")
        sys.modules["maix"] = fake_maix
        try:
            MaixRtspBackend(VideoSettings())
        finally:
            if original is None:
                del sys.modules["maix"]
            else:
                sys.modules["maix"] = original
        self.assertEqual(
            events,
            [
                "key_listener_removed",
                "uart_listener_removed",
                "camera_created",
                "camera_bound",
            ],
        )


if __name__ == "__main__":
    unittest.main()
