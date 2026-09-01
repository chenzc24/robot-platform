"""L1 tests for the simulator-only desktop control-console shell."""

import os
import pathlib
import sys
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "console"))

from PySide6.QtWidgets import QApplication

from ui.controller import ConsoleController
from ui.models import Environment, Lifecycle, LinkState
from ui.views import MainWindow


class ConsoleControllerTests(unittest.TestCase):
    def setUp(self):
        self.controller = ConsoleController()

    def _ready_chassis(self):
        self.assertTrue(self.controller.connect_chassis())
        self.assertTrue(self.controller.chassis_acquire())
        self.assertTrue(self.controller.chassis_enable())
        self.assertTrue(self.controller.set_chassis_manual_unlock(True))

    def _ready_arm(self):
        self.assertTrue(self.controller.connect_arm())
        self.assertTrue(self.controller.set_arm_manual_unlock(True))

    def test_safe_defaults_lock_every_motion_path(self):
        state = self.controller.state
        self.assertEqual(state.environment, Environment.SIMULATOR)
        self.assertEqual(state.video.link, LinkState.OFFLINE)
        self.assertFalse(state.chassis.motion_enabled)
        self.assertFalse(state.chassis.manual_unlocked)
        self.assertFalse(state.arm.manual_unlocked)
        self.assertFalse(self.controller.can_chassis_move())
        self.assertFalse(self.controller.can_arm_move())
        self.assertFalse(self.controller.chassis_velocity(1, 0, 0))

    def test_chassis_simulator_requires_session_then_stops_on_release(self):
        self._ready_chassis()
        self.assertTrue(self.controller.can_chassis_move())
        self.assertTrue(self.controller.chassis_velocity(80, 0, 0))
        self.assertEqual(self.controller.state.chassis.velocity, (80, 0, 0))
        self.assertTrue(self.controller.chassis_stop())
        self.assertEqual(self.controller.state.chassis.velocity, (0, 0, 0))
        self.controller.chassis_release()
        self.assertFalse(self.controller.can_chassis_move())
        self.assertEqual(self.controller.state.chassis.velocity, (0, 0, 0))

    def test_video_failure_does_not_prevent_simulated_chassis_stop(self):
        self._ready_chassis()
        self.assertTrue(self.controller.chassis_velocity(80, 0, 0))
        self.controller.set_scenario("video_stale")
        self.assertFalse(self.controller.connect_video())
        self.assertEqual(self.controller.state.video.link, LinkState.DEGRADED)
        self.assertTrue(self.controller.chassis_stop())
        self.assertEqual(self.controller.state.chassis.velocity, (0, 0, 0))

    def test_arm_unknown_locks_further_non_idempotent_actions(self):
        self._ready_arm()
        self.controller.set_scenario("arm_unknown")
        self.assertFalse(self.controller.execute_arm("arm.move_joint", "joint_deg=[0,0,0,0,0,0]"))
        self.assertEqual(self.controller.state.arm.task, Lifecycle.UNKNOWN)
        self.assertFalse(self.controller.state.arm.manual_unlocked)
        self.assertTrue(any(fault.code == "arm_outcome_unknown" for fault in self.controller.state.faults))
        self.assertFalse(self.controller.execute_arm("arm.move_joint", "joint_deg=[0,0,0,0,0,0]"))
        self.assertEqual(self.controller.events[0].lifecycle, Lifecycle.REJECTED)

    def test_hardware_mode_has_no_adapter_and_never_reports_a_real_connection(self):
        self.controller.set_environment(Environment.HARDWARE)
        self.assertFalse(self.controller.connect_chassis())
        self.assertFalse(self.controller.connect_arm())
        self.assertFalse(self.controller.connect_video())
        self.assertEqual(self.controller.state.chassis.link, LinkState.OFFLINE)
        self.assertEqual(self.controller.state.arm.gateway, LinkState.OFFLINE)
        self.assertFalse(self.controller.chassis_stop())
        self.assertTrue(any(fault.code == "hardware_adapter_unavailable" for fault in self.controller.state.faults))

    def test_normal_arm_lifecycle_requires_explicit_completion(self):
        self._ready_arm()
        self.assertTrue(self.controller.execute_arm("arm.move_joint", "joint_deg=[0,0,0,0,0,0]"))
        self.assertEqual(self.controller.state.arm.task, Lifecycle.RUNNING)
        self.assertTrue(self.controller.complete_arm_command())
        self.assertEqual(self.controller.state.arm.task, Lifecycle.IDLE)
        self.assertEqual(self.controller.events[0].lifecycle, Lifecycle.DONE)
        lifecycle_events = self.controller.events[:3]
        self.assertEqual(
            {event.lifecycle for event in lifecycle_events},
            {Lifecycle.ACCEPTED, Lifecycle.RUNNING, Lifecycle.DONE},
        )
        self.assertEqual(len({event.correlation_id for event in lifecycle_events}), 1)


class ConsoleWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication(["control-console-tests"])

    def test_window_constructs_with_safe_controls_disabled(self):
        window = MainWindow()
        try:
            window.run_smoke_assertions()
            self.assertFalse(window.joint_execute_button.isEnabled())
            self.assertFalse(window.chassis_enable_button.isEnabled())
            self.assertIn("Simulator", window.windowTitle())
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
