"""L1 tests for the localhost console without real device connections."""

import json
import pathlib
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "console"))

from localization.state_machine import RailLocalizationStateMachine
from runtime_config import ArmConfig, ChassisConfig, ManualChassisConfig, RuntimeConfig, VideoConfig
from web_console.runtime import WebConsoleError, WebConsoleRuntime
from web_console.server import create_server


def config(manual=True):
    return RuntimeConfig(
        chassis=ChassisConfig("esp32.invalid", 4242, 1.0, "console", "TEST_CREDENTIAL"),
        manual_chassis=ManualChassisConfig(manual, 500, 300, 600, 800),
        arm=ArmConfig("maixcam.invalid", 4343, 1.0, "console"),
        video=VideoConfig("", "http://127.0.0.1:8889/maixcam/", 1.0, ""),
    )


def localization_vision_result(sequence):
    return {
        "accepted": True,
        "pose_solved": True,
        "camera_calibration_ready": True,
        "board_layout_ready": True,
        "calibration_id": "calibration-a",
        "layout_id": "layout-a",
        "board_frame": "apriltag_board",
        "frame_sequence": sequence,
        "captured_at_ms": sequence * 10,
        "used_ids": [0, 1, 2, 3],
        "confidence": 0.95,
        "reprojection_rmse_px": 0.2,
        "T_board_from_camera": [
            [1.0, 0.0, 0.0, 10.0],
            [0.0, 1.0, 0.0, 20.0],
            [0.0, 0.0, 1.0, 30.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
    }


class Connection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeChassis:
    def __init__(self):
        self.connection = Connection()
        self.enabled = False
        self.calls = []

    def _response(self, response_type, sequence=1, payload=None):
        return {"version": 3, "sequence": sequence, "type": response_type, "ttl_ms": 0, "payload": payload or {}}

    def ping(self):
        self.calls.append(("ping",))
        return self._response("PONG")

    def status(self):
        self.calls.append(("status",))
        return self._response("STATE", payload={
            "service_state": "ready", "chassis_state": "enabled_stopped" if self.enabled else "disabled",
            "motion_permitted": True, "authenticated": True, "hold_remaining_ms": 0, "last_error": "none",
        })

    def enable(self):
        self.calls.append(("enable",)); self.enabled = True
        return self._response("DONE")

    def velocity(self, vx, vy, omega, hold):
        self.calls.append(("velocity", vx, vy, omega, hold))
        return self._response("DONE")

    def stop(self):
        self.calls.append(("stop",))
        return self._response("DONE")

    def disable(self):
        self.calls.append(("disable",)); self.enabled = False
        return self._response("DONE")


def arm_status(service_state="ready", permitted=True, feedback_valid=True, sample_id=1, feedback_error="none"):
    joint = "1,2,3,4,5,6" if feedback_valid else "unavailable"
    pose = "101,202,303,1.5,2.5,3.5" if feedback_valid else "unavailable"
    downstream = ";".join((
        "service_state=" + service_state,
        "motion_enabled=" + ("1" if permitted else "0"),
        "control_mode=yolo", "active_sequence=0", "last_error=none",
        "terminal_position_supported=0", "cancel_supported=0",
        "feedback_valid=" + ("1" if feedback_valid else "0"),
        "feedback_error=" + feedback_error,
        "joint_deg=" + joint, "pose=" + pose,
        "pose_user=0", "pose_tool=0", "sample_id=" + str(sample_id), "sample_time_ms=1234",
    ))
    return [{
        "version": 1, "kind": "lifecycle", "message_id": "reply-1", "sequence": 1,
        "target": "arm", "name": "arm.status", "ttl_ms": 0,
        "payload": {"downstream_sequence": 1, "terminal_position": None, "downstream_payload": downstream},
        "correlation_id": "console-1", "lifecycle": "DONE",
    }]


class FakeArm:
    def __init__(self):
        self.connection = Connection()
        self.calls = []
        self.status_result = None

    def status(self):
        self.calls.append(("status",)); return self.status_result or arm_status()

    def ping(self):
        self.calls.append(("ping",)); return arm_status()

    def jog_joint(self, values, accel, speed):
        self.calls.append(("jog_joint", values, accel, speed)); return [{"lifecycle": "DONE", "payload": {}}]

    def jog_xyz(self, values, user, tool, accel, speed):
        self.calls.append(("jog_xyz", values, user, tool, accel, speed)); return [{"lifecycle": "DONE", "payload": {}}]

    def move_joint(self, values, accel, speed):
        self.calls.append(("move_joint", values, accel, speed)); return [{"lifecycle": "DONE", "payload": {}}]

    def move_linear(self, values, user, tool, accel, speed):
        self.calls.append(("move_linear", values, user, tool, accel, speed)); return [{"lifecycle": "DONE", "payload": {}}]

    def gripper(self, width):
        self.calls.append(("gripper", width)); return [{"lifecycle": "DONE", "payload": {}}]


class ExplicitRejection(RuntimeError):
    explicit_rejection = True
    code = "invalid_chassis_state"


class RejectingChassis(FakeChassis):
    def enable(self):
        raise ExplicitRejection("invalid_chassis_state")


class WebRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.chassis = FakeChassis()
        self.arm = FakeArm()
        self.runtime = WebConsoleRuntime(config(), lambda _config: self.chassis, lambda _config: self.arm, start_workers=False)

    def tearDown(self):
        self.runtime.close()

    def test_chassis_connect_enable_hold_refresh_stop_and_disconnect(self):
        self.runtime.connect_chassis()
        self.assertEqual(self.runtime.snapshot()["chassis"]["link"], "online")
        self.runtime.enable_chassis()
        self.assertTrue(self.runtime.snapshot()["chassis"]["motion_enabled"])
        self.runtime.start_chassis_motion({"vx_mm_s": 300, "vy_mm_s": 400, "omega_mrad_s": 700,
            "input_mode": "momentary", "motion_epoch": self.runtime.snapshot()["chassis"]["motion"]["epoch"]})
        self.runtime.motion_once()
        velocities = [call for call in self.chassis.calls if call[0] == "velocity"]
        self.assertEqual(len(velocities), 2)
        self.assertEqual(velocities[-1][1:], (300, 400, 700, 300))
        self.runtime.stop_chassis_motion()
        self.assertEqual(self.runtime.snapshot()["chassis"]["velocity"], {"vx_mm_s": 0, "vy_mm_s": 0, "omega_mrad_s": 0})
        self.runtime.disconnect_chassis()
        self.assertTrue(self.chassis.connection.closed)

    def test_velocity_range_and_manual_switch_are_enforced_locally(self):
        self.runtime.connect_chassis(); self.runtime.enable_chassis()
        with self.assertRaisesRegex(WebConsoleError, "velocity_out_of_range"):
            self.runtime.start_chassis_motion({"vx_mm_s": 600, "vy_mm_s": 600, "omega_mrad_s": 0})
        disabled = WebConsoleRuntime(config(manual=False), lambda _config: FakeChassis(), lambda _config: FakeArm(), start_workers=False)
        try:
            disabled.connect_chassis()
            with self.assertRaisesRegex(WebConsoleError, "manual_chassis_disabled"):
                disabled.enable_chassis()
        finally:
            disabled.close()

    def test_explicit_chassis_rejection_does_not_drop_link(self):
        runtime = WebConsoleRuntime(config(), lambda _config: RejectingChassis(), lambda _config: FakeArm(), start_workers=False)
        try:
            runtime.connect_chassis()
            with self.assertRaisesRegex(WebConsoleError, "invalid_chassis_state"):
                runtime.enable_chassis()
            self.assertEqual(runtime.snapshot()["chassis"]["link"], "online")
            self.assertEqual(runtime.snapshot()["faults"], [])
        finally:
            runtime.close()

    def test_double_connect_creates_only_one_client_per_route(self):
        chassis_calls, arm_calls = [], []
        runtime = WebConsoleRuntime(
            config(),
            lambda _config: chassis_calls.append(FakeChassis()) or chassis_calls[-1],
            lambda _config: arm_calls.append(FakeArm()) or arm_calls[-1],
            start_workers=False,
        )
        try:
            threads = [threading.Thread(target=runtime.connect_chassis) for _ in range(2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            threads = [threading.Thread(target=runtime.connect_arm) for _ in range(2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            self.assertEqual(len(chassis_calls), 1)
            self.assertEqual(len(arm_calls), 1)
        finally:
            runtime.close()

    def test_slow_arm_poll_does_not_delay_chassis_heartbeats(self):
        blocked, release, heartbeats_seen = threading.Event(), threading.Event(), threading.Event()
        heartbeats = []
        self.runtime.connect_chassis()
        self.runtime.connect_arm()
        original_status = self.arm.status
        original_ping = self.chassis.ping

        def slow_status():
            blocked.set()
            release.wait(4)
            return original_status()

        def observed_ping():
            if blocked.is_set() and not release.is_set():
                heartbeats.append(1)
                if len(heartbeats) >= 3:
                    heartbeats_seen.set()
            return original_ping()

        self.arm.status = slow_status
        self.chassis.ping = observed_ping
        try:
            self.runtime._start_workers()
            self.assertTrue(blocked.wait(1.5))
            self.assertTrue(heartbeats_seen.wait(2.5))
            self.assertGreaterEqual(len(heartbeats), 3)
        finally:
            release.set()

    def test_background_arm_poll_skips_an_occupied_route(self):
        owned, release = threading.Event(), threading.Event()
        self.runtime.connect_arm()

        def operator_call():
            with self.runtime._arm_io:
                owned.set()
                release.wait(2)

        worker = threading.Thread(target=operator_call)
        worker.start()
        try:
            self.assertTrue(owned.wait(1))
            calls_before = len(self.arm.calls)
            self.runtime.arm_health_once()
            self.assertEqual(len(self.arm.calls), calls_before)
        finally:
            release.set()
            worker.join(2)

    def test_arm_controls_are_independent_and_validate_precise_vectors(self):
        self.runtime.connect_arm()
        self.runtime.arm_command("jog_joint", {"joint_delta_deg": [2, 0, 0, 0, 0, 0], "speed_pct": 20, "accel_pct": 20})
        self.runtime.arm_command("jog_xyz", {"translation_mm": [0, -5, 0], "user": 0, "tool": 0, "speed_pct": 20, "accel_pct": 20})
        self.assertEqual(self.arm.calls[-2][0], "jog_joint")
        self.assertEqual(self.arm.calls[-1][0], "jog_xyz")
        self.assertEqual(self.runtime.snapshot()["chassis"]["link"], "offline")
        with self.assertRaisesRegex(WebConsoleError, "invalid_arm_vector"):
            self.runtime.arm_command("jog_joint", {"joint_delta_deg": [2]})

    def test_arm_measurement_is_exposed_aged_and_never_replaced_by_target(self):
        clock = [10.0]
        runtime = WebConsoleRuntime(
            config(), lambda _config: FakeChassis(), lambda _config: self.arm,
            start_workers=False, clock=lambda: clock[0],
        )
        try:
            runtime.connect_arm()
            measured = runtime.snapshot()["arm"]["measurement"]
            self.assertTrue(measured["valid"])
            self.assertEqual(measured["joint_deg"], [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
            self.assertEqual(measured["pose"], [101.0, 202.0, 303.0, 1.5, 2.5, 3.5])
            clock[0] = 10.25
            self.assertEqual(runtime.snapshot()["arm"]["measurement"]["age_ms"], 250)
            runtime.arm_command("move_joint", {"joint_deg": [9, 9, 9, 9, 9, 9]})
            self.assertEqual(runtime.snapshot()["arm"]["measurement"]["joint_deg"], [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
            self.arm.status_result = arm_status("ready", True, False, 2, "feedback_read_failed")
            runtime.refresh_arm_status()
            stale = runtime.snapshot()["arm"]["measurement"]
            self.assertFalse(stale["valid"])
            self.assertEqual(stale["joint_deg"], [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
            self.assertEqual(stale["error"], "feedback_read_failed")
        finally:
            runtime.close()

    def test_text_log_contains_only_sanitized_event_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "events.log"
            runtime = WebConsoleRuntime(config(), lambda _config: FakeChassis(), lambda _config: FakeArm(), start_workers=False, event_log_path=path)
            try:
                runtime.connect_chassis()
                content = path.read_text(encoding="utf-8")
            finally:
                runtime.close()
        self.assertIn("EVENT target=ESP32 command=connect", content)
        self.assertNotIn("TEST_CREDENTIAL", content)
        self.assertNotIn("esp32.invalid", content)

    def test_localization_locks_exposes_task_context_and_invalidates_on_motion(self):
        clock = [10.0]
        machine = RailLocalizationStateMachine(
            enabled=True,
            rail_axis="x",
            json_axis="x",
            json_origin_rail_position_mm=5.0,
            json_mm_per_rail_mm=-1.0,
            settle_time_ms=100,
            sample_window_ms=1000,
            min_valid_samples=2,
            min_visible_tags=2,
            clock=lambda: clock[0],
        )
        runtime = WebConsoleRuntime(
            config(), lambda _config: self.chassis, lambda _config: self.arm,
            start_workers=False, clock=lambda: clock[0], localization_machine=machine,
        )
        try:
            runtime.connect_chassis()
            runtime.enable_chassis()
            self.assertEqual(runtime.snapshot()["localization"]["state"], "settling")
            clock[0] += 0.11
            runtime._on_vision_update(localization_vision_result(1))
            runtime._on_vision_update(localization_vision_result(2))
            locked = runtime.snapshot()["localization"]
            self.assertEqual(locked["state"], "locked")
            self.assertTrue(locked["valid"])
            lock_events = [event for event in runtime.snapshot()["events"] if event["target"] == "Localization"]
            self.assertTrue(any(event["lifecycle"] == "DONE" and "state=locked" in event["result"] for event in lock_events))
            self.assertTrue(any("json_axis_offset_mm=-5.0" in event["result"] for event in lock_events))
            context = runtime.begin_localized_task("draw-1", locked["generation"])
            self.assertEqual(context["rail_position_mm"], 10.0)
            self.assertEqual(context["json_axis_offset_mm"], -5.0)
            runtime.finish_localized_task("draw-1", "DONE", "complete")

            epoch = runtime.snapshot()["chassis"]["motion"]["epoch"]
            runtime.start_chassis_motion({
                "vx_mm_s": 1,
                "vy_mm_s": 0,
                "omega_mrad_s": 0,
                "input_mode": "momentary",
                "motion_epoch": epoch,
            })
            invalidated = runtime.snapshot()["localization"]
            self.assertEqual(invalidated["state"], "moving")
            self.assertFalse(invalidated["valid"])
            with self.assertRaisesRegex(WebConsoleError, "localization_not_locked"):
                runtime.localized_task_context(locked["generation"])
        finally:
            runtime.close()


class WebServerTests(unittest.TestCase):
    def setUp(self):
        self.runtime = WebConsoleRuntime(config(), start_workers=False)
        self.server = create_server(self.runtime, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(1)
        self.runtime.close()

    def _request(self, path, data=None, origin=None):
        headers = {} if origin is None else {"Origin": origin}
        if data is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(data).encode("utf-8")
        return urllib.request.urlopen(urllib.request.Request(self.base + path, data=data, headers=headers), timeout=2)

    def test_serves_compact_console_and_sanitized_state(self):
        html = self._request("/").read().decode("utf-8")
        self.assertIn("Live view", html)
        self.assertIn("EXACT VECTOR", html)
        self.assertIn("ROBOT ARM", html)
        self.assertIn("Measured robot arm position", html)
        self.assertIn('id="vision-canvas"', html)
        response = json.load(self._request("/api/state"))
        self.assertTrue(response["ok"])
        self.assertEqual(response["state"]["vision"]["status"], "disabled")
        self.assertNotIn("credential", json.dumps(response))

    def test_rejects_non_loopback_origin_and_unknown_paths(self):
        with self.assertRaises(urllib.error.HTTPError) as rejected:
            self._request("/api/chassis/stop", {}, "https://attacker.example")
        self.assertEqual(rejected.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as missing:
            self._request("/../secret")
        self.assertEqual(missing.exception.code, 404)

    def test_offline_stop_is_idempotent_and_does_not_connect(self):
        response = json.load(self._request("/api/chassis/stop", {}, self.base))
        self.assertTrue(response["ok"])
        self.assertEqual(response["state"]["chassis"]["link"], "offline")

    def test_relocalize_route_fails_closed_when_localization_is_disabled(self):
        with self.assertRaises(urllib.error.HTTPError) as rejected:
            self._request("/api/localization/relocalize", {}, self.base)
        self.assertEqual(rejected.exception.code, 409)
        body = json.load(rejected.exception)
        self.assertEqual(body["error"], "localization_disabled")

    def test_server_refuses_non_loopback_binding(self):
        with self.assertRaisesRegex(ValueError, "loopback"):
            create_server(self.runtime, "0.0.0.0", 0)


if __name__ == "__main__":
    unittest.main()
