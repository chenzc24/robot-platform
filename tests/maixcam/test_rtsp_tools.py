"""Static tests for the MaixCam RTSP sender and host probe configuration."""

import importlib.util
import pathlib
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]


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


if __name__ == "__main__":
    unittest.main()
