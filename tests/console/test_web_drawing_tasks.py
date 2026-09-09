"""L1 drawing-task lifecycle and Web ownership tests with fake execution only."""

import json
import pathlib
import sys
import tempfile
import threading
import unittest
import urllib.request
from dataclasses import replace
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "console"))

from test_web_console import FakeArm, FakeChassis, config
from runtime_config import LocalizationConfig, VisionConfig
from web_console.drawing_tasks import DrawingTaskError, DrawingTaskManager
from web_console.runtime import WebConsoleError, WebConsoleRuntime
from web_console.server import create_server


def task_files(directory):
    root = pathlib.Path(directory)
    drawing = json.loads((ROOT / "config" / "drawing.example.json").read_text(encoding="utf-8"))
    drawing["production_ready"] = True
    drawing["relocation"]["selected_mode"] = "baseline"
    drawing["rail"]["json_origin_rail_position_mm"] = -100.0
    (root / "drawing.json").write_text(json.dumps(drawing), encoding="utf-8")
    (root / "job.json").write_bytes((ROOT / "dataset" / "dobot-generation-1.json").read_bytes())
    policy = {
        "version": 1,
        "jobs": {"sample": "job.json"},
        "execution_log_directory": "logs",
    }
    (root / "web.json").write_text(json.dumps(policy), encoding="utf-8")
    return root / "drawing.json", root / "web.json"


def two_window_job(path):
    document = json.loads((path).read_text(encoding="utf-8"))
    strokes = (
        {"id": "left", "order": 1, "points": [[0.10, 0.5], [0.12, 0.5]], "closed": False},
        {"id": "right", "order": 1, "points": [[0.88, 0.5], [0.90, 0.5]], "closed": False},
    )
    document["groups"] = [
        {"name": "黄色", "strokes": [strokes[0]]},
        {"name": "紫色", "strokes": [strokes[1]]},
    ]
    path.write_text(json.dumps(document), encoding="utf-8")


class FakeDrawingLocalization:
    def __init__(self, offsets=None):
        self.generation = 1
        self.offset = 100.0
        self.offsets = list(offsets or ())
        self.tasks = []

    def snapshot(self, *_args):
        return {
            "state": "locked",
            "reason": "stable_pose_window",
            "revision": self.generation,
            "valid": True,
            "generation": self.generation,
            "context": {
                "generation": self.generation,
                "rail_position_mm": -self.offset,
                "json_axis_offset_mm": self.offset,
                "json_mm_per_rail_mm": -1.0,
                "source": {"min_confidence": 0.95},
            },
        }

    def on_chassis_status(self, _state):
        return None

    def on_chassis_unavailable(self, _reason):
        return None

    def on_motion_intent(self, *_args):
        return None

    def request_relocalization(self):
        self.generation += 1
        self.offset = self.offsets.pop(0) if self.offsets else -100.0

    def begin_task(self, task_id, generation=None):
        self.tasks.append(("begin", task_id, generation))
        return self.snapshot()["context"]

    def finish_task(self, task_id, outcome, result):
        self.tasks.append(("finish", task_id, outcome, result))


class FakeAdvancedChassis(FakeChassis):
    def line_follow_start(self, direction):
        self.calls.append(("line_follow_start", direction))
        return self._response("DONE")

    def line_follow_status(self):
        self.calls.append(("line_follow_status",))
        return self._response("STATE", payload={"state": "station"})

    def line_follow_stop(self):
        self.calls.append(("line_follow_stop",))
        return self._response("DONE")


class DrawingTaskManagerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.drawing, self.policy = task_files(self.root)
        self.started = threading.Event()
        self.released = threading.Event()
        self.acquired = []

        def execute(prepared, _attended, cancel, emit):
            self.started.set()
            emit({"event": "fake_window_start", "mode": prepared.mode})
            cancel.wait(2)
            if cancel.is_set():
                raise DrawingTaskError("drawing_cancelled")
            return {"windows": 1}

        self.manager = DrawingTaskManager(
            self.root,
            self.drawing,
            self.policy,
            execute,
            lambda prepared: self.acquired.append(prepared.mode),
            self.released.set,
            lambda: None,
            lambda mode, _control: mode == "baseline",
        )

    def tearDown(self):
        self.manager.close()
        self.temporary.cleanup()

    def set_mode(self, mode):
        drawing = json.loads(self.drawing.read_text(encoding="utf-8"))
        drawing["relocation"]["selected_mode"] = mode
        self.drawing.write_text(json.dumps(drawing), encoding="utf-8")

    def test_prepare_snapshots_real_job_and_mode_specific_readiness(self):
        baseline = self.manager.prepare({
            "action": "prepare", "job_id": "sample", "mode": "baseline",
        })
        self.assertEqual(baseline["state"], "prepared")
        self.assertEqual(baseline["strokes"], 439)
        self.assertEqual(baseline["points"], 3903)
        self.assertTrue(all(baseline["readiness"].values()))

        self.set_mode("localized_baseline")
        localized = self.manager.prepare({
            "action": "prepare", "job_id": "sample", "mode": "localized_baseline",
        })
        self.assertEqual(localized["mode"], "localized_baseline")
        self.assertFalse(localized["readiness"]["runtime"])
        with self.assertRaisesRegex(DrawingTaskError, "drawing_mode_not_production_ready"):
            self.manager.start({
                "action": "start",
                "task_id": localized["task_id"],
                "attended": True,
            })

    def test_running_task_locks_mode_and_cancel_releases_owner(self):
        prepared = self.manager.prepare({
            "action": "prepare", "job_id": "sample", "mode": "baseline",
        })
        running = self.manager.start({
            "action": "start",
            "task_id": prepared["task_id"],
            "attended": True,
        })
        self.assertEqual(running["state"], "running")
        self.assertTrue(self.started.wait(1))
        with self.assertRaisesRegex(DrawingTaskError, "drawing_mode_locked_while_active"):
            self.manager.prepare({
                "action": "prepare", "job_id": "sample", "mode": "advanced",
            })
        stopping = self.manager.cancel({"action": "cancel", "task_id": prepared["task_id"]})
        self.assertEqual(stopping["state"], "stopping")
        final = self.manager.wait(2)
        self.assertEqual(final["state"], "cancelled")
        self.assertTrue(self.released.is_set())
        self.set_mode("advanced")
        switched = self.manager.prepare({
            "action": "prepare", "job_id": "sample", "mode": "advanced",
        })
        self.assertEqual(switched["mode"], "advanced")

    def test_start_requires_only_current_task_and_attended_confirmation(self):
        prepared = self.manager.prepare({
            "action": "prepare", "job_id": "sample", "mode": "baseline",
        })
        with self.assertRaisesRegex(DrawingTaskError, "drawing_attended_confirmation_required"):
            self.manager.start({
                "action": "start", "task_id": prepared["task_id"],
                "attended": False,
            })
        with self.assertRaisesRegex(DrawingTaskError, "drawing_task_id_mismatch"):
            self.manager.start({
                "action": "start", "task_id": "stale", "attended": True,
            })

    def test_prepare_and_start_requests_are_lifecycle_serialized(self):
        prepared = self.manager.handle({
            "action": "prepare", "job_id": "sample", "mode": "baseline",
        })
        entered, release = threading.Event(), threading.Event()
        errors = []
        from web_console import drawing_tasks as module
        original_load = module.load_drawing_site_config
        self.set_mode("advanced")

        def slow_load(path):
            entered.set()
            release.wait(2)
            return original_load(path)

        with mock.patch.object(module, "load_drawing_site_config", slow_load):
            prepare_thread = threading.Thread(target=lambda: self.manager.handle({
                "action": "prepare", "job_id": "sample", "mode": "advanced",
            }))

            def stale_start():
                try:
                    self.manager.handle({
                        "action": "start", "task_id": prepared["task_id"],
                        "attended": True,
                    })
                except DrawingTaskError as error:
                    errors.append(error.code)

            prepare_thread.start()
            self.assertTrue(entered.wait(1))
            start_thread = threading.Thread(target=stale_start)
            start_thread.start()
            self.assertEqual(self.acquired, [])
            release.set()
            prepare_thread.join(2)
            start_thread.join(2)
        self.assertEqual(errors, ["drawing_task_id_mismatch"])
        self.assertEqual(self.manager.snapshot()["mode"], "advanced")


class WebDrawingOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.drawing, self.policy = task_files(self.root)
        self.runtime = WebConsoleRuntime(
            config(), lambda _config: FakeChassis(), lambda _config: FakeArm(),
            start_workers=False,
        )
        self.execution_started = threading.Event()

        def fake_execute(_prepared, _attended, cancel, _emit):
            self.execution_started.set()
            cancel.wait(2)
            if cancel.is_set():
                raise DrawingTaskError("drawing_cancelled")
            return {"windows": 1}

        self.runtime._execute_drawing_task = fake_execute
        self.runtime.configure_drawing_tasks(
            self.root, self.drawing, self.policy,
        )

    def tearDown(self):
        self.runtime.close()
        self.temporary.cleanup()

    def _start(self):
        state = self.runtime.drawing_task({
            "action": "prepare", "job_id": "sample", "mode": "baseline",
        })["drawing"]
        self.runtime.drawing_task({
            "action": "start", "task_id": state["task_id"],
            "attended": True,
        })
        self.assertTrue(self.execution_started.wait(1))
        return state

    def test_drawing_owner_rejects_manual_connections_and_commands(self):
        state = self._start()
        self.assertEqual(self.runtime.snapshot()["control_owner"], "drawing")
        with self.assertRaisesRegex(WebConsoleError, "drawing_task_owns_devices"):
            self.runtime.connect_chassis()
        with self.assertRaisesRegex(WebConsoleError, "drawing_task_owns_devices"):
            self.runtime.connect_arm()
        with self.assertRaisesRegex(WebConsoleError, "drawing_task_owns_devices"):
            self.runtime.arm_command("gripper", {"width_mm": 20})
        with self.assertRaisesRegex(WebConsoleError, "drawing_task_owns_devices"):
            self.runtime.request_relocalization()
        self.runtime.drawing_task({"action": "cancel", "task_id": state["task_id"]})
        self.runtime._drawing_tasks.wait(2)
        self.assertEqual(self.runtime.snapshot()["control_owner"], "none")

    def test_global_chassis_stop_cancels_the_active_drawing_task(self):
        self._start()
        self.runtime.stop_chassis_motion()
        final = self.runtime._drawing_tasks.wait(2)
        self.assertEqual(final["state"], "cancelled")
        self.assertEqual(self.runtime.snapshot()["control_owner"], "none")

    def test_global_chassis_stop_invalidates_a_prepared_task(self):
        prepared = self.runtime.drawing_task({
            "action": "prepare", "job_id": "sample", "mode": "baseline",
        })["drawing"]
        self.runtime.stop_chassis_motion()
        self.assertEqual(self.runtime.snapshot()["drawing"]["state"], "cancelled")
        with self.assertRaisesRegex(WebConsoleError, "drawing_task_not_prepared"):
            self.runtime.drawing_task({
                "action": "start", "task_id": prepared["task_id"],
                "attended": True,
            })

    def test_out_of_tolerance_start_fails_before_arm_connection(self):
        site = json.loads(self.drawing.read_text(encoding="utf-8"))
        site["relocation"]["selected_mode"] = "localized_baseline"
        self.drawing.write_text(json.dumps(site), encoding="utf-8")
        runtime_config = replace(
            config(),
            vision=VisionConfig(
                True, "board.json", "camera.json", "DICT_APRILTAG_36H11",
            ),
            localization=LocalizationConfig(
                enabled=True, json_mm_per_rail_mm=-1.0,
            ),
        )
        localization = FakeDrawingLocalization()
        localization.offset = 0.0  # rail position 0; configured r0 is -100 mm.
        arm_connections = []
        runtime = WebConsoleRuntime(
            runtime_config,
            lambda _config: FakeChassis(),
            lambda _config: arm_connections.append(True) or FakeArm(),
            start_workers=False,
            localization_machine=localization,
        )
        try:
            runtime.configure_drawing_tasks(
                self.root, self.drawing, self.policy,
            )
            prepared = runtime.drawing_task({
                "action": "prepare", "job_id": "sample",
                "mode": "localized_baseline",
            })["drawing"]
            runtime.drawing_task({
                "action": "start", "task_id": prepared["task_id"],
                "job_sha256": prepared["job_sha256"], "attended": True,
            })
            final = runtime._drawing_tasks.wait(2)
            self.assertEqual(final["state"], "failed")
            self.assertIn("drawing_start_outside_tolerance", final["error"])
            self.assertEqual(arm_connections, [])
        finally:
            runtime.close()

    def test_runtime_executes_one_small_window_through_shared_fake_sessions(self):
        document = json.loads((self.root / "job.json").read_text(encoding="utf-8"))
        document["groups"] = [{
            **document["groups"][0],
            "strokes": [document["groups"][0]["strokes"][0]],
        }]
        (self.root / "job.json").write_text(json.dumps(document), encoding="utf-8")
        chassis, arm = FakeChassis(), FakeArm()
        runtime = WebConsoleRuntime(
            config(), lambda _config: chassis, lambda _config: arm,
            start_workers=False,
        )
        try:
            runtime.configure_drawing_tasks(
                self.root, self.drawing, self.policy,
            )
            prepared = runtime.drawing_task({
                "action": "prepare", "job_id": "sample", "mode": "baseline",
            })["drawing"]
            runtime.drawing_task({
                "action": "start", "task_id": prepared["task_id"],
                "attended": True,
            })
            final = runtime._drawing_tasks.wait(4)
            self.assertEqual(final["state"], "completed")
            self.assertEqual(final["result"]["windows"], 1)
            self.assertEqual(runtime.snapshot()["control_owner"], "manual_ui")
            self.assertIn(("enable",), chassis.calls)
            self.assertIn(("disable",), chassis.calls)
            self.assertTrue(any(call[0] == "move_joint" for call in arm.calls))
            self.assertTrue(any(call[0] == "gripper" for call in arm.calls))
        finally:
            runtime.close()

    def test_connected_manual_sessions_are_taken_over_and_restored(self):
        self.runtime.connect_chassis()
        self.runtime.connect_arm()
        self.assertEqual(self.runtime.snapshot()["control_owner"], "manual_ui")
        state = self._start()
        self.assertEqual(self.runtime.snapshot()["control_owner"], "drawing")
        self.runtime.drawing_task({"action": "cancel", "task_id": state["task_id"]})
        self.runtime._drawing_tasks.wait(2)
        self.assertEqual(self.runtime.snapshot()["control_owner"], "manual_ui")

    def test_localized_and_advanced_modes_execute_relocation_via_shared_sessions(self):
        two_window_job(self.root / "job.json")
        drawing = json.loads(self.drawing.read_text(encoding="utf-8"))
        drawing["relocation"]["baseline"].update(speed_mm_s=600, settle_ms=0)
        self.drawing.write_text(json.dumps(drawing), encoding="utf-8")
        runtime_config = replace(
            config(),
            vision=VisionConfig(
                True, "board.json", "camera.json", "DICT_APRILTAG_36H11",
            ),
            localization=LocalizationConfig(
                enabled=True, json_mm_per_rail_mm=-1.0,
            ),
        )
        for mode in ("localized_baseline", "advanced"):
            with self.subTest(mode=mode):
                drawing = json.loads(self.drawing.read_text(encoding="utf-8"))
                drawing["relocation"]["selected_mode"] = mode
                self.drawing.write_text(json.dumps(drawing), encoding="utf-8")
                chassis = FakeAdvancedChassis()
                arm = FakeArm()
                localization = (
                    FakeDrawingLocalization((-40.0, -60.0, -200.0, -220.0))
                    if mode == "localized_baseline"
                    else FakeDrawingLocalization()
                )
                runtime = WebConsoleRuntime(
                    runtime_config,
                    lambda _config, value=chassis: value,
                    lambda _config, value=arm: value,
                    start_workers=False,
                    localization_machine=localization,
                )
                try:
                    runtime.configure_drawing_tasks(
                        self.root, self.drawing, self.policy,
                    )
                    prepared = runtime.drawing_task({
                        "action": "prepare", "job_id": "sample", "mode": mode,
                    })["drawing"]
                    self.assertTrue(all(prepared["readiness"].values()))
                    runtime.drawing_task({
                        "action": "start", "task_id": prepared["task_id"],
                        "attended": True,
                    })
                    final = runtime._drawing_tasks.wait(10)
                    self.assertEqual(final["state"], "completed", final)
                    self.assertEqual(
                        final["result"]["windows"],
                        3 if mode == "localized_baseline" else 2,
                    )
                    self.assertEqual(
                        len(final["result"]["relocations"]),
                        2 if mode == "localized_baseline" else 1,
                    )
                    self.assertEqual(
                        localization.generation,
                        5 if mode == "localized_baseline" else 2,
                    )
                    if mode == "localized_baseline":
                        self.assertTrue(any(call[0] == "velocity" for call in chassis.calls))
                    else:
                        self.assertIn(("line_follow_start", 1), chassis.calls)
                        self.assertIn(("line_follow_stop",), chassis.calls)
                finally:
                    runtime.close()


class WebDrawingRouteTests(unittest.TestCase):
    def test_configured_http_route_prepares_allowlisted_job_without_devices(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            drawing, policy = task_files(root)
            runtime = WebConsoleRuntime(config(), start_workers=False)
            runtime.configure_drawing_tasks(root, drawing, policy)
            server = create_server(runtime, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = "http://127.0.0.1:%d" % server.server_address[1]
            try:
                body = json.dumps({
                    "action": "prepare", "job_id": "sample", "mode": "baseline",
                }).encode("utf-8")
                request = urllib.request.Request(
                    base + "/api/drawing/task",
                    data=body,
                    headers={"Content-Type": "application/json", "Origin": base},
                )
                result = json.load(urllib.request.urlopen(request, timeout=2))
                self.assertTrue(result["ok"])
                self.assertEqual(result["state"]["drawing"]["state"], "prepared")
                self.assertEqual(result["state"]["drawing"]["strokes"], 439)
                self.assertEqual(result["state"]["control_owner"], "none")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(1)
                runtime.close()


if __name__ == "__main__":
    unittest.main()
