"""Offline concurrency and HTTP regressions for operator motion lifetime."""

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from test_web_console import FakeChassis, config
from web_console.runtime import WebConsoleError, WebConsoleRuntime
from web_console.server import create_server


class HoldLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.client = FakeChassis()
        self.temp = tempfile.TemporaryDirectory()
        self.log = Path(self.temp.name) / "events.log"
        self.runtime = WebConsoleRuntime(config(), lambda _: self.client, start_workers=False,
                                         clock=lambda: self.now, event_log_path=self.log)
        self.runtime.connect_chassis()
        self.runtime.enable_chassis()

    def tearDown(self):
        self.runtime.close()
        self.temp.cleanup()

    def payload(self, mode="momentary", **values):
        return {"vx_mm_s": 50, "vy_mm_s": 0, "omega_mrad_s": 0,
                "motion_epoch": self.runtime.snapshot()["chassis"]["motion"]["epoch"],
                "input_mode": mode, **values}

    def start(self, mode="momentary"):
        return self.runtime.start_chassis_motion(self.payload(mode))["chassis"]["motion"]["epoch"]

    def assert_idle(self):
        self.assertIsNone(self.runtime._held_velocity)
        self.assertEqual(self.runtime.snapshot()["chassis"]["motion"]["mode"], "idle")
        self.assertEqual(self.runtime.snapshot()["chassis"]["velocity"]["vx_mm_s"], 0)
        count = len(self.client.calls)
        for _ in range(4):
            self.runtime.motion_once()
        self.assertEqual(len(self.client.calls), count)

    def run_paused_velocity(self, action, refreshing=False):
        if refreshing:
            self.start()
        payload = self.payload()
        entered, resume, cancelled = threading.Event(), threading.Event(), threading.Event()
        errors = []
        original_velocity, original_cancel = self.client.velocity, self.runtime._cancel_motion

        def velocity(*args):
            result = original_velocity(*args)
            entered.set()
            if not resume.wait(3):
                raise RuntimeError("test_resume_timeout")
            return result

        def cancel(reason, stopping=False):
            result = original_cancel(reason, stopping)
            if stopping:
                cancelled.set()
            return result

        def run_motion():
            try:
                if refreshing:
                    self.runtime.motion_once()
                else:
                    self.runtime.start_chassis_motion(payload)
            except WebConsoleError as error:
                errors.append(error.code)

        self.client.velocity, self.runtime._cancel_motion = velocity, cancel
        move = threading.Thread(target=run_motion)
        stop = threading.Thread(target=action)
        try:
            move.start()
            self.assertTrue(entered.wait(2))
            stop.start()
            self.assertTrue(cancelled.wait(2))
            self.assertIsNone(self.runtime._held_velocity)
        finally:
            resume.set()
            move.join(3)
            if stop.ident:
                stop.join(3)
        self.assertFalse(move.is_alive() or stop.is_alive())
        self.assertEqual(errors, [] if refreshing else ["motion_cancelled"])
        self.assert_idle()
        names = [call[0] for call in self.client.calls]
        self.assertLess(max(i for i, name in enumerate(names) if name == "velocity"), names.index("stop") if "stop" in names else names.index("disable"))

    def test_stop_cancels_start_waiting_for_velocity_reply(self):
        self.run_paused_velocity(self.runtime.stop_chassis_motion)

    def test_disable_cancels_start_and_does_not_revive_on_enable(self):
        self.run_paused_velocity(self.runtime.disable_chassis)
        self.runtime.enable_chassis()
        self.assert_idle()

    def test_disconnect_cancels_start_and_does_not_revive_on_reconnect(self):
        self.run_paused_velocity(self.runtime.disconnect_chassis)
        self.runtime.connect_chassis()
        self.runtime.enable_chassis()
        self.assert_idle()

    def test_inflight_refresh_finishes_before_stop_not_after_it(self):
        self.run_paused_velocity(self.runtime.stop_chassis_motion, refreshing=True)

    def test_worker_queued_for_io_cannot_send_copied_velocity_after_stop(self):
        self.start()
        original = self.runtime._chassis_io
        waiting = threading.Event()

        class ObservedLock:
            def __enter__(self):
                if threading.current_thread().name == "queued-refresh":
                    waiting.set()
                return original.__enter__()

            def __exit__(self, *args):
                return original.__exit__(*args)

        self.runtime._chassis_io = ObservedLock()
        with original:
            thread = threading.Thread(target=self.runtime.motion_once, name="queued-refresh")
            thread.start()
            self.assertTrue(waiting.wait(2))
            self.runtime.stop_chassis_motion()
            count = len(self.client.calls)
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(self.client.calls), count)
        self.assert_idle()

    def test_stop_before_start_http_arrival_rejects_old_epoch_without_velocity(self):
        payload = self.payload()
        self.runtime.stop_chassis_motion()
        count = len(self.client.calls)
        with self.assertRaisesRegex(WebConsoleError, "stale_motion_epoch"):
            self.runtime.start_chassis_motion(payload)
        self.assertEqual(len(self.client.calls), count)

    def test_duplicate_start_and_old_keepalive_do_not_replace_new_input(self):
        old = self.payload("hold")
        first = self.runtime.start_chassis_motion(old)["chassis"]["motion"]["epoch"]
        second = self.start()
        for action in (lambda: self.runtime.start_chassis_motion(old),
                       lambda: self.runtime.keep_chassis_motion({"motion_epoch": first})):
            with self.assertRaisesRegex(WebConsoleError, "stale_motion_epoch"):
                action()
        self.assertEqual(self.runtime.snapshot()["chassis"]["motion"]["epoch"], second)
        self.assertEqual(self.runtime.snapshot()["chassis"]["motion"]["mode"], "momentary")

    def test_presence_and_refresh_are_distinct_and_expire_in_both_modes(self):
        for mode in ("momentary", "hold"):
            with self.subTest(mode=mode):
                epoch = self.start(mode)
                self.now += 0.8
                self.runtime.keep_chassis_motion({"motion_epoch": epoch})
                self.now += 0.8
                self.runtime.motion_once()
                self.assertIsNotNone(self.runtime._held_velocity)
                self.now += 0.21
                self.runtime.motion_once()
                self.assert_idle()
                self.assertEqual(self.runtime.snapshot()["chassis"]["motion"]["reason"], "browser_input_expired")
                self.assertTrue(self.client.enabled)

    def test_late_keepalive_cannot_renew_expired_input_even_before_worker_tick(self):
        epoch = self.start()
        self.now += 1.001
        with self.assertRaisesRegex(WebConsoleError, "motion_input_expired"):
            self.runtime.keep_chassis_motion({"motion_epoch": epoch})
        self.assert_idle()
        with self.assertRaisesRegex(WebConsoleError, "stale_motion_epoch"):
            self.runtime.keep_chassis_motion({"motion_epoch": epoch})

    def test_start_reply_delayed_past_presence_budget_stops_without_latching(self):
        original = self.client.velocity

        def delayed(*args):
            self.now += 1.1
            return original(*args)

        self.client.velocity = delayed
        with self.assertRaisesRegex(WebConsoleError, "motion_input_expired"):
            self.start()
        self.assert_idle()
        self.assertIn(("stop",), self.client.calls)

    def test_refresh_rejection_is_logged_and_clears_hold_without_dropping_link(self):
        self.start()

        class Rejected(Exception):
            explicit_rejection = True
            code = "invalid_chassis_state"

        def rejected(*args):
            raise Rejected()

        self.client.velocity = rejected
        self.runtime.motion_once()
        self.assert_idle()
        self.assertEqual(self.runtime.snapshot()["chassis"]["link"], "online")
        self.assertIn("motion.refresh lifecycle=FAULT", self.log.read_text())

    def test_connection_failure_clears_hold_and_never_retries_velocity(self):
        self.start()

        def failed(*args):
            raise OSError("fake link loss")

        self.client.velocity = failed
        self.runtime.motion_once()
        self.assert_idle()
        self.assertEqual(self.runtime.snapshot()["chassis"]["link"], "offline")

    def test_failed_replacement_stops_previous_vector_and_clears_hold(self):
        self.start("hold")

        class Rejected(Exception):
            explicit_rejection = True
            code = "invalid_chassis_state"

        def rejected(*args):
            raise Rejected()

        self.client.velocity = rejected
        with self.assertRaisesRegex(WebConsoleError, "invalid_chassis_state"):
            self.start()
        self.assert_idle()
        self.assertIn(("stop",), self.client.calls)

    def test_missing_metadata_and_wrong_mode_do_not_write_velocity(self):
        for updates in ({"motion_epoch": None}, {"input_mode": "unknown"}, {"input_mode": None}):
            before = len(self.client.calls)
            with self.assertRaisesRegex(WebConsoleError, "motion_metadata_required"):
                self.runtime.start_chassis_motion(self.payload(**updates))
            self.assertEqual(len(self.client.calls), before)

    def test_keepalive_alone_sends_no_device_command(self):
        epoch = self.start()
        count = len(self.client.calls)
        self.runtime.keep_chassis_motion({"motion_epoch": epoch})
        self.assertEqual(len(self.client.calls), count)

    def test_unwritable_log_cannot_prevent_stop(self):
        self.start()
        self.runtime._event_log_path = Path(self.temp.name)
        self.runtime.stop_chassis_motion()
        self.assert_idle()
        self.assertIn(("stop",), self.client.calls)
        self.assertIsNotNone(self.runtime.snapshot()["log_error"])

    def test_device_disabled_status_clears_refresh_and_new_enable_is_idle(self):
        self.start()
        self.client.enabled = False
        self.runtime.refresh_chassis_status()
        self.runtime.enable_chassis()
        self.assert_idle()

    def test_log_records_mode_epoch_clear_reason_and_refresh_summary(self):
        epoch = self.start("hold")
        for _ in range(3):
            self.runtime.motion_once()
        self.runtime.stop_chassis_motion(reason="pointer_release")
        content = self.log.read_text()
        self.assertIn("epoch=" + epoch, content)
        self.assertIn("mode=hold reason=pointer_release refreshes=3", content)
        self.assertNotIn("TEST_CREDENTIAL", content)
        self.assertEqual(content.count("command=velocity"), 1)

    def test_http_motion_metadata_and_keepalive_route(self):
        server = create_server(self.runtime, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:%d" % server.server_address[1]

        def post(path, body):
            request = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                             headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=2) as response:
                return json.load(response)

        try:
            result = post("/api/chassis/motion/start", self.payload("hold"))
            epoch = result["state"]["chassis"]["motion"]["epoch"]
            self.assertTrue(post("/api/chassis/motion/keepalive", {"motion_epoch": epoch})["ok"])
            post("/api/chassis/stop", {"reason": "pointer_release"})
            with self.assertRaises(urllib.error.HTTPError) as rejected:
                post("/api/chassis/motion/keepalive", {"motion_epoch": epoch})
            self.assertEqual(rejected.exception.code, 409)
            self.assert_idle()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)


if __name__ == "__main__":
    unittest.main()
