"""Static tests for the MaixCam RTSP sender and host probe configuration."""

import importlib.util
import pathlib
import sys
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
VIDEO_DIR = ROOT / "src" / "maixcam" / "video"
sys.path.insert(0, str(VIDEO_DIR))


def load_module(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RtspServerSettingsTests(unittest.TestCase):
    def setUp(self):
        self.server = load_module("maixcam_rtsp_server", "src/maixcam/video/rtsp_server.py")

    def test_safe_development_defaults(self):
        args = self.server.build_parser().parse_args([])
        self.server.validate_settings(args)
        self.assertEqual((args.width, args.height, args.fps), (1280, 720, 20))
        self.assertEqual(args.port, 8554)
        self.assertEqual(args.bitrate, 2_000_000)

    def test_invalid_settings_are_rejected_without_importing_maix(self):
        args = self.server.build_parser().parse_args(["--fps", "0"])
        with self.assertRaises(ValueError):
            self.server.validate_settings(args)

    def test_stop_handlers_are_registered_after_backend_initialization(self):
        args = self.server.build_parser().parse_args([])
        service = mock.Mock()
        handlers = {}

        def backend_start():
            # Simulate native imports replacing previously installed handlers.
            handlers.clear()

        service.start.side_effect = backend_start

        def register(signum, handler):
            handlers[signum] = handler

        def tick(_seconds):
            self.assertIn(self.server.signal.SIGTERM, handlers)
            self.assertIn(self.server.signal.SIGINT, handlers)
            handlers[self.server.signal.SIGTERM](self.server.signal.SIGTERM, None)

        with mock.patch.object(self.server.signal, "signal", side_effect=register), \
                mock.patch.object(self.server.time, "sleep", side_effect=tick):
            self.server.run(args, service_factory=lambda **_kwargs: service)
        service.start.assert_called_once_with()
        service.stop.assert_called_once_with()


class RtspProbeSettingsTests(unittest.TestCase):
    def setUp(self):
        self.probe = load_module("maixcam_rtsp_probe", "tools/maixcam/rtsp_probe.py")

    def test_probe_defaults_use_mdns_and_rtsp(self):
        args = self.probe.build_parser().parse_args([])
        self.probe.validate_settings(args)
        self.assertEqual(args.url, "rtsp://maixcam-6c7d.local:8554/live")
        self.assertEqual(args.transport, "tcp")

    def test_mdns_url_is_resolved_to_ipv4(self):
        with mock.patch.object(
            self.probe.socket,
            "getaddrinfo",
            return_value=[(2, 1, 6, "", ("192.0.2.20", 8554))],
        ):
            resolved = self.probe.resolve_ipv4_url(
                "rtsp://maixcam-6c7d.local:8554/live"
            )
        self.assertEqual(resolved, "rtsp://192.0.2.20:8554/live")

    def test_non_rtsp_url_is_rejected(self):
        args = self.probe.build_parser().parse_args(["--url", "http://example.invalid/live"])
        with self.assertRaises(ValueError):
            self.probe.validate_settings(args)


class MediaRelayConfigurationTests(unittest.TestCase):
    def test_console_media_dependencies_include_numpy(self):
        requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
        self.assertIn("av==", requirements)
        self.assertIn("numpy==", requirements)

    def test_mediamtx_accepts_only_the_local_ffmpeg_publisher(self):
        config = (ROOT / "config/mediamtx.example.yml").read_text(encoding="utf-8")
        self.assertIn("source: publisher", config)
        self.assertNotIn("maixcam-6c7d.local", config)
        self.assertNotIn("10.114.", config)

    def test_relay_uses_copy_mode_instead_of_transcoding(self):
        wrapper = (ROOT / "tools/maixcam/mediamtx.ps1").read_text(encoding="utf-8")
        self.assertIn('"-c:v", "copy"', wrapper)
        self.assertIn("mediamtx-v1.20.0", wrapper)
        self.assertIn("ffmpeg-9.0.1", wrapper)

    def test_relay_waits_for_the_published_path_to_be_ready(self):
        wrapper = (ROOT / "tools/maixcam/mediamtx.ps1").read_text(encoding="utf-8")
        self.assertIn("function Wait-RelayReady", wrapper)
        self.assertIn("/v3/paths/list", wrapper)
        self.assertIn('$path.ready -and $path.online', wrapper)
        self.assertIn("VIDEO_RELAY_NOT_READY", wrapper)

    def test_relay_accepts_an_ipv4_literal_without_dns_lookup(self):
        wrapper = (ROOT / "tools/maixcam/mediamtx.ps1").read_text(encoding="utf-8")
        self.assertIn("[System.Net.IPAddress]::TryParse", wrapper)
        self.assertIn("AddressFamily]::InterNetwork", wrapper)


class DeviceLifecycleScriptTests(unittest.TestCase):
    def _script(self, name):
        return (VIDEO_DIR / name).read_text(encoding="ascii")

    def test_start_refuses_vendor_launcher_before_importing_maixpy(self):
        script = self._script("start.sh")
        refusal = script.index("RTSP_START_REFUSED launcher_active")
        launch = script.index('nohup python3 -u "$video_dir/rtsp_server.py"')
        self.assertLess(refusal, launch)
        self.assertIn('readlink "$proc_path/exe"', script)

    def test_start_waits_for_a_structured_ready_event(self):
        start = self._script("start.sh")
        self.assertIn("pid_matches_server", start)
        self.assertIn('"event": "rtsp_started"', start)
        self.assertIn("RTSP_START_TIMEOUT", start)
        self.assertIn('nohup python3 -u "$video_dir/rtsp_server.py"', start)

    def test_start_timeout_retains_live_process_ownership(self):
        start = self._script("start.sh")
        cleanup = start.split('echo "RTSP_START_TIMEOUT', 1)[1]
        self.assertIn('if pid_matches_server "$new_pid"; then', cleanup)
        self.assertIn("pid_file_retained", cleanup)
        self.assertIn('else\n    rm -f "$pid_file"\nfi', cleanup)

    def test_stop_refuses_to_signal_an_unowned_pid(self):
        stop = self._script("stop.sh")
        self.assertIn("pid_matches_server", stop)
        self.assertIn("RTSP_STOP_REFUSED ownership_mismatch", stop)
        self.assertNotIn("kill -9", stop)

    def test_status_is_read_only_and_checks_process_ownership(self):
        status = self._script("status.sh")
        self.assertIn("/proc/$pid/cmdline", status)
        self.assertIn("RTSP_RUNNING", status)
        self.assertNotIn('kill "$pid"', status)


if __name__ == "__main__":
    unittest.main()
