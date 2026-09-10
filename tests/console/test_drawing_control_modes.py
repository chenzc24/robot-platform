"""Deterministic tests for explicit baseline and advanced relocation modes."""

import pathlib
import sys
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/console"))

from drawing.control_modes import (
    RelocationAdmission,
    create_relocator,
    parse_drawing_control_config,
    relocate_reposition_plan,
)
from drawing.models import DrawingError


def config_document(mode="baseline", ready=True, version=1):
    document = {
        "version": version,
        "production_ready": ready,
        "selected_mode": mode,
        "json_mm_per_rail_mm": -1.0,
        "baseline": {
            "initial_json_axis_offset_mm": 0,
            "speed_mm_s": 50,
            "refresh_ms": 100,
            "hold_ms": 250,
            "max_distance_mm": 300,
            "settle_ms": 2000,
        },
        "advanced": {
            "poll_ms": 100,
            "station_timeout_ms": 1000,
            "localization_timeout_ms": 1000,
        },
    }
    if version >= 2:
        document["localized_baseline"] = {
            "poll_ms": 100,
            "localization_timeout_ms": 1000,
        }
    if version == 3:
        document["localized_baseline"].update({
            "normal_window_advance_mm": 160,
            "coarse_approach_reserve_mm": 20,
            "micro_adjust_speed_mm_s": 20,
            "micro_adjust_max_step_mm": 20,
            "micro_adjust_tolerance_mm": 3,
            "micro_adjust_max_attempts": 3,
        })
    return document


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeChassis:
    def __init__(self, line_states=None):
        self.calls = []
        self.line_states = list(line_states or [])

    def velocity(self, *args):
        self.calls.append(("velocity", args))

    def stop(self):
        self.calls.append(("stop", ()))

    def ping(self):
        self.calls.append(("ping", ()))

    def status(self):
        self.calls.append(("status", ()))
        return {
            "version": 3, "sequence": 10, "type": "STATE", "ttl_ms": 0,
            "payload": {
                "service_state": "ready", "chassis_state": "enabled_stopped",
                "motion_permitted": True, "authenticated": True,
                "hold_remaining_ms": 0, "last_error": "none",
            },
        }

    def line_follow_start(self, direction):
        self.calls.append(("line_follow_start", (direction,)))

    def line_follow_status(self):
        state = self.line_states.pop(0)
        self.calls.append(("line_follow_status", ()))
        return {"payload": {"state": state, "reason": state, "direction": 1}}

    def line_follow_stop(self):
        self.calls.append(("line_follow_stop", ()))


class FakeLocalization:
    def __init__(self):
        self.requested = False
        self.after = 0

    def snapshot(self):
        if not self.requested:
            return {
                "state": "locked", "generation": 2,
                "context": {
                    "json_axis_offset_mm": 0.0,
                    "json_mm_per_rail_mm": -1.0,
                },
            }
        self.after += 1
        if self.after == 1:
            return {"state": "collecting", "generation": 2, "context": None}
        return {
            "state": "locked",
            "generation": 3,
            "context": {
                "generation": 3,
                "json_axis_offset_mm": -42.5,
                "json_mm_per_rail_mm": -1.0,
                "rail_position_mm": 42.5,
                "source": {"min_confidence": 0.91},
            },
        }

    def request_relocalization(self):
        self.requested = True

    def on_motion_intent(self, reason):
        self.motion_reason = reason

    def on_chassis_status(self, state):
        self.chassis_state = state


class ScriptedLocalization:
    """A new AprilTag generation is available after every commanded stop."""

    def __init__(self, offsets):
        self.offsets = list(offsets)
        self.generation = 2
        self.offset = 0.0
        self.requested = False
        self.calls = []

    def snapshot(self):
        if self.requested:
            self.generation += 1
            self.requested = False
            self.offset = self.offsets.pop(0)
        return {
            "state": "locked", "generation": self.generation,
            "context": {
                "generation": self.generation,
                "json_axis_offset_mm": self.offset,
                "json_mm_per_rail_mm": -1.0,
                "rail_position_mm": -self.offset,
                "source": {"min_confidence": 0.91},
            },
        }

    def request_relocalization(self):
        self.requested = True

    def on_motion_intent(self, reason):
        self.calls.append((reason, 0.0))

    def on_chassis_status(self, _state):
        pass


def admission(**overrides):
    values = {
        "attended": True,
        "arm_safe": True,
        "chassis_state": "enabled_stopped",
    }
    values.update(overrides)
    return RelocationAdmission(**values)


class DrawingControlConfigTests(unittest.TestCase):
    def test_mode_and_bounded_timing_are_strict(self):
        config = parse_drawing_control_config(config_document())
        self.assertEqual(config.selected_mode, "baseline")
        for mutation in ("mode", "scale", "refresh", "extra"):
            document = config_document()
            if mutation == "mode":
                document["selected_mode"] = "automatic"
            elif mutation == "scale":
                document["json_mm_per_rail_mm"] = 0
            elif mutation == "refresh":
                document["baseline"]["refresh_ms"] = 250
            else:
                document["unexpected"] = True
            with self.subTest(mutation=mutation), self.assertRaises(DrawingError):
                parse_drawing_control_config(document)

    def test_version_two_adds_only_explicit_localized_baseline(self):
        config = parse_drawing_control_config(
            config_document("localized_baseline", version=2)
        )
        self.assertEqual(config.selected_mode, "localized_baseline")
        self.assertEqual(config.localized_baseline.poll_ms, 100)
        with self.assertRaisesRegex(DrawingError, "not available"):
            parse_drawing_control_config(config_document("localized_baseline"))

    def test_legacy_baseline_defaults_initial_offset_to_zero(self):
        document = config_document()
        del document["baseline"]["initial_json_axis_offset_mm"]
        config = parse_drawing_control_config(document)
        self.assertEqual(config.baseline.initial_json_axis_offset_mm, 0)


class BaselineRelocatorTests(unittest.TestCase):
    def test_configured_chassis_sign_maps_positive_rail_to_negative_vx(self):
        clock = FakeClock()
        chassis = FakeChassis()
        document = config_document()
        document["baseline"]["chassis_vx_sign"] = -1
        config = parse_drawing_control_config(document)
        relocator = create_relocator(
            config, chassis, clock=clock, sleep=clock.sleep
        )
        relocator.relocate(0, -10, admission())
        velocity = next(call for call in chassis.calls if call[0] == "velocity")
        self.assertEqual(velocity[1][0], -50)

    def test_direct_distance_refreshes_stops_and_reports_open_loop_offset(self):
        clock = FakeClock()
        chassis = FakeChassis()
        config = parse_drawing_control_config(config_document())
        relocator = create_relocator(
            config, chassis, clock=clock, sleep=clock.sleep
        )
        result = relocator.relocate(5, -10, admission())
        self.assertEqual(result.mode, "baseline")
        self.assertEqual(result.offset_source, "commanded_open_loop")
        self.assertEqual(result.commanded_rail_distance_mm, 10)
        self.assertEqual(result.json_axis_offset_mm, -5)
        self.assertIsNone(result.confidence)
        self.assertEqual([name for name, _ in chassis.calls], ["velocity", "velocity", "stop"])

    def test_admission_readiness_and_distance_limit_block_before_motion(self):
        for document, gate, code in (
            (config_document(ready=False), admission(), "not_production_ready"),
            (config_document(), admission(arm_safe=False), "requires_arm_safe"),
            (config_document(), admission(), "distance_exceeds_limit"),
        ):
            chassis = FakeChassis()
            config = parse_drawing_control_config(document)
            relocator = create_relocator(config, chassis)
            delta = -301 if code == "distance_exceeds_limit" else -10
            with self.subTest(code=code), self.assertRaisesRegex(DrawingError, code):
                relocator.relocate(0, delta, gate)
            self.assertEqual(chassis.calls, [])

    def test_motion_failure_still_attempts_stop(self):
        class Failing(FakeChassis):
            def velocity(self, *args):
                self.calls.append(("velocity", args))
                raise RuntimeError("lost")

        clock = FakeClock()
        chassis = Failing()
        config = parse_drawing_control_config(config_document())
        with self.assertRaisesRegex(DrawingError, "baseline_motion_failed"):
            create_relocator(config, chassis, clock=clock, sleep=clock.sleep).relocate(0, -10, admission())
        self.assertEqual(chassis.calls[-1][0], "stop")

    def test_planner_barrier_returns_checkpoint_and_new_offset(self):
        clock = FakeClock()
        chassis = FakeChassis()
        config = parse_drawing_control_config(config_document())
        relocator = create_relocator(config, chassis, clock=clock, sleep=clock.sleep)
        checkpoint = types.SimpleNamespace(to_dict=lambda: {
            "group_index": 1,
            "stroke_index": 2,
            "next_point_index": 3,
        })
        plan = types.SimpleNamespace(
            complete=False,
            next_checkpoint=checkpoint,
            json_axis_offset_mm=5,
            steps=(types.SimpleNamespace(
                kind="reposition.required",
                payload={"suggested_json_axis_offset_delta_mm": -10},
            ),),
        )
        resume = relocate_reposition_plan(plan, relocator, admission())
        self.assertEqual(resume["json_axis_offset_mm"], -5)
        self.assertEqual(resume["checkpoint"]["next_point_index"], 3)

    def test_planner_barrier_bounds_long_centering_move_to_one_direct_hop(self):
        clock = FakeClock()
        chassis = FakeChassis()
        config = parse_drawing_control_config(config_document())
        relocator = create_relocator(config, chassis, clock=clock, sleep=clock.sleep)
        checkpoint = types.SimpleNamespace(to_dict=lambda: {
            "group_index": 2,
            "stroke_index": 0,
            "next_point_index": 0,
        })
        plan = types.SimpleNamespace(
            complete=False,
            next_checkpoint=checkpoint,
            json_axis_offset_mm=-6,
            steps=(types.SimpleNamespace(
                kind="reposition.required",
                payload={"suggested_json_axis_offset_delta_mm": 480},
            ),),
        )

        resume = relocate_reposition_plan(plan, relocator, admission())

        self.assertEqual(resume["json_axis_offset_mm"], 294)
        self.assertEqual(
            resume["relocation"]["commanded_rail_distance_mm"], -300
        )


class AdvancedRelocatorTests(unittest.TestCase):
    def test_station_then_fresh_localization_is_the_only_offset_source(self):
        clock = FakeClock()
        chassis = FakeChassis(["following", "station"])
        localization = FakeLocalization()
        config = parse_drawing_control_config(config_document("advanced"))
        result = create_relocator(
            config,
            chassis,
            localization,
            clock=clock,
            sleep=clock.sleep,
        ).relocate(0, -50, admission())
        self.assertEqual(result.offset_source, "apriltag_locked")
        self.assertEqual(result.json_axis_offset_mm, -42.5)
        self.assertEqual(result.localization_generation, 3)
        self.assertEqual(result.confidence, 0.91)
        self.assertTrue(localization.requested)
        names = [name for name, _ in chassis.calls]
        self.assertIn("line_follow_stop", names)
        self.assertIn("ping", names)

    def test_line_fault_stops_and_never_uses_direct_velocity_fallback(self):
        clock = FakeClock()
        chassis = FakeChassis(["fault"])
        config = parse_drawing_control_config(config_document("advanced"))
        with self.assertRaisesRegex(DrawingError, "advanced_line_follow_fault"):
            create_relocator(
                config,
                chassis,
                FakeLocalization(),
                clock=clock,
                sleep=clock.sleep,
            ).relocate(0, -50, admission())
        self.assertNotIn("velocity", [name for name, _ in chassis.calls])
        self.assertEqual(chassis.calls[-1][0], "line_follow_stop")

    def test_localization_scale_mismatch_blocks_before_chassis_motion(self):
        class Mismatched(FakeLocalization):
            def snapshot(self):
                return {
                    "state": "locked",
                    "generation": 2,
                    "context": {"json_mm_per_rail_mm": 1.0},
                }

        chassis = FakeChassis(["station"])
        config = parse_drawing_control_config(config_document("advanced"))
        with self.assertRaisesRegex(DrawingError, "scale_mismatch"):
            create_relocator(config, chassis, Mismatched()).relocate(
                0, -50, admission()
            )
        self.assertEqual(chassis.calls, [])


class LocalizedBaselineRelocatorTests(unittest.TestCase):
    def test_v2_localized_config_gets_conservative_compatibility_defaults(self):
        config = parse_drawing_control_config(
            config_document("localized_baseline", version=2)
        )
        settings = config.localized_baseline
        self.assertEqual(settings.normal_window_advance_mm, 160)
        self.assertEqual(settings.coarse_approach_reserve_mm, 20)
        self.assertEqual(settings.micro_adjust_speed_mm_s, 50)
        self.assertEqual(settings.micro_adjust_max_step_mm, 20)
        self.assertEqual(settings.micro_adjust_tolerance_mm, 3)
        self.assertEqual(settings.micro_adjust_max_attempts, 3)

    def test_target_cap_coarse_approach_and_fresh_micro_adjust_locks(self):
        clock = FakeClock()
        chassis = FakeChassis()
        localization = ScriptedLocalization((-138.0, -158.5))
        document = config_document("localized_baseline", version=3)
        document["baseline"]["chassis_vx_sign"] = -1
        config = parse_drawing_control_config(document)
        events = []
        relocator = create_relocator(
            config, chassis, localization, clock=clock, sleep=clock.sleep,
            event=events.append,
        )
        self.assertEqual(relocator.barrier_delta(-180), -160)
        result = relocator.relocate(0, -160, admission())
        self.assertEqual(result.mode, "localized_baseline")
        self.assertEqual(result.offset_source, "apriltag_micro_adjusted")
        self.assertEqual(result.commanded_rail_distance_mm, 160)
        self.assertEqual(result.json_axis_offset_mm, -158.5)
        self.assertEqual(result.localization_generation, 4)
        self.assertEqual(
            [event["commanded_rail_distance_mm"] for event in events
             if event["state"] in (
                 "localized_baseline_start",
                 "localized_baseline_micro_adjust_start",
             )],
            [140, 20],
        )
        self.assertEqual(
            [name for name, _ in chassis.calls].count("stop"), 2
        )
        self.assertEqual(
            [name for name, _ in chassis.calls].count("status"), 2
        )
        velocities = [args[0] for name, args in chassis.calls if name == "velocity"]
        self.assertIn(-50, velocities)
        self.assertEqual(velocities[-1], -20)
        self.assertEqual(len(localization.calls), 2)

    def test_micro_adjustment_rejects_no_progress_before_resume(self):
        clock = FakeClock()
        chassis = FakeChassis()
        localization = ScriptedLocalization((-138.0, -137.0))
        config = parse_drawing_control_config(
            config_document("localized_baseline", version=3)
        )
        with self.assertRaisesRegex(DrawingError, "micro_adjust_no_progress"):
            create_relocator(
                config, chassis, localization, clock=clock, sleep=clock.sleep
            ).relocate(0, -160, admission())
        self.assertEqual([name for name, _ in chassis.calls].count("stop"), 2)

    def test_micro_adjustment_stops_after_configured_attempt_limit(self):
        clock = FakeClock()
        chassis = FakeChassis()
        localization = ScriptedLocalization((-140.0, -150.0))
        document = config_document("localized_baseline", version=3)
        document["localized_baseline"]["micro_adjust_max_attempts"] = 1
        config = parse_drawing_control_config(document)
        with self.assertRaisesRegex(DrawingError, "micro_adjust_exhausted"):
            create_relocator(
                config, chassis, localization, clock=clock, sleep=clock.sleep
            ).relocate(0, -160, admission())
        self.assertEqual([name for name, _ in chassis.calls].count("stop"), 2)

    def test_unconfirmed_stop_blocks_localization_and_resume(self):
        class MovingAfterStop(FakeChassis):
            def status(self):
                response = super().status()
                response["payload"]["chassis_state"] = "moving"
                return response

        clock = FakeClock()
        chassis = MovingAfterStop()
        localization = FakeLocalization()
        config = parse_drawing_control_config(
            config_document("localized_baseline", version=3)
        )
        with self.assertRaisesRegex(DrawingError, "not_stopped"):
            create_relocator(
                config, chassis, localization, clock=clock, sleep=clock.sleep
            ).relocate(0, -10, admission())
        self.assertFalse(localization.requested)


if __name__ == "__main__":
    unittest.main()
