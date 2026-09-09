"""No-device rehearsal that executes the production Localized Baseline path."""

import math
from dataclasses import replace

from .control_modes import RelocationAdmission, parse_drawing_control_config
from .coordinator import execute_drawing
from .executor import DrawingExecutionAdmission
from .loader import canonical_document
from .models import DrawingError, PlanCheckpoint
from .planner import build_drawing_plan


_ARM_STATUS = (
    "service_state=ready;motion_enabled=1;control_mode=yolo;active_sequence=0;"
    "last_error=none;terminal_position_supported=0;cancel_supported=0;"
    "feedback_valid=1;feedback_error=none;joint_deg=1,2,3,4,5,6;"
    "pose=1,2,3,4,5,6;pose_user=0;pose_tool=0;sample_id=1;sample_time_ms=0"
)


def _finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DrawingError("%s must be a finite number" % label)
    value = float(value)
    if not math.isfinite(value):
        raise DrawingError("%s must be a finite number" % label)
    return value


def _clean(value):
    value = round(float(value), 9)
    return 0.0 if value == 0 else value


def _checkpoint(value):
    if value is None:
        return None
    return PlanCheckpoint(
        value["group_index"], value["stroke_index"], value["next_point_index"]
    )


def _point_rank(job, checkpoint):
    if checkpoint is None:
        return 0
    rank = 0
    for group_index, group in enumerate(job.groups):
        for stroke_index, stroke in enumerate(group.strokes):
            if (
                group_index == checkpoint.group_index
                and stroke_index == checkpoint.stroke_index
            ):
                return rank + checkpoint.next_point_index
            rank += len(stroke.points)
    raise DrawingError("simulation checkpoint is outside the drawing")


def _simulation_drawing_config(config, reachable_min_mm, reachable_max_mm):
    geometry = config.geometry
    low = (
        geometry.reachable_home_relative_y_min_mm
        if reachable_min_mm is None
        else _finite(reachable_min_mm, "reachable_min_mm")
    )
    high = (
        geometry.reachable_home_relative_y_max_mm
        if reachable_max_mm is None
        else _finite(reachable_max_mm, "reachable_max_mm")
    )
    if low >= high:
        raise DrawingError("simulated reachable User-Y minimum must be below maximum")
    return replace(
        config,
        production_ready=True,
        geometry=replace(
            geometry,
            reachable_home_relative_y_min_mm=low,
            reachable_home_relative_y_max_mm=high,
        ),
    )


def _default_control_config(scale):
    return parse_drawing_control_config({
        "version": 2,
        "production_ready": True,
        "selected_mode": "localized_baseline",
        "json_mm_per_rail_mm": scale,
        "baseline": {
            "initial_json_axis_offset_mm": 0.0,
            "speed_mm_s": 50,
            "refresh_ms": 100,
            "hold_ms": 250,
            "max_distance_mm": 300.0,
            "settle_ms": 2000,
        },
        "localized_baseline": {
            "poll_ms": 100,
            "localization_timeout_ms": 10000,
        },
        "advanced": {
            "poll_ms": 100,
            "station_timeout_ms": 30000,
            "localization_timeout_ms": 10000,
        },
    })


def _simulation_control_config(config, scale_override):
    if config is None:
        scale = -1.0 if scale_override is None else scale_override
        return _default_control_config(scale)
    if config.localized_baseline is None:
        raise DrawingError("simulation requires drawing control schema version 2")
    scale = config.json_mm_per_rail_mm if scale_override is None else scale_override
    return replace(
        config,
        production_ready=True,
        selected_mode="localized_baseline",
        json_mm_per_rail_mm=scale,
    )


def _safety_sequence(plan):
    result = []
    if any(
        step.kind == "arm.relative" and step.payload.get("purpose") == "pen_up"
        for step in plan.steps[:-1]
    ):
        result.append("pen_up")
    if any(
        step.kind == "pen.return" and "for reposition" in step.label
        for step in plan.steps[:-1]
    ):
        result.append("pen_return")
    if not any(
        step.kind == "arm.home"
        and step.payload.get("purpose") == "reposition_safe_pose"
        for step in plan.steps[:-1]
    ):
        raise DrawingError("simulation barrier has no safe-home step")
    result.append("arm_home_safe")
    return result


class _SimulationClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += _finite(seconds, "simulation sleep")


class _SimulationArm:
    """Successful arm endpoint with the exact production client surface."""

    def __init__(self):
        self.calls = []

    @staticmethod
    def _done(name):
        return [{"lifecycle": "DONE", "name": name, "payload": {}}]

    def ping(self):
        self.calls.append("ping")
        return self._done("arm.ping")

    def status(self):
        self.calls.append("status")
        return [{
            "version": 1,
            "kind": "lifecycle",
            "message_id": "simulation-reply",
            "sequence": 1,
            "target": "arm",
            "name": "arm.status",
            "ttl_ms": 0,
            "payload": {
                "downstream_sequence": 1,
                "terminal_position": "unknown",
                "downstream_payload": _ARM_STATUS,
            },
            "correlation_id": "simulation-request",
            "lifecycle": "DONE",
        }]

    def _motion(self, name):
        self.calls.append(name)
        return self._done(name)

    def move_joint(self, *_args, **_kwargs):
        return self._motion("move_joint")

    def jog_xyz(self, *_args, **_kwargs):
        return self._motion("jog_xyz")

    def draw_stroke(self, *_args, **_kwargs):
        return self._motion("draw_stroke")

    def gripper(self, *_args, **_kwargs):
        return self._motion("gripper")


class _SimulationChassis:
    """Integrate production VELOCITY timing into a deterministic true position."""

    def __init__(
        self, clock, initial_position_mm, motion_gain, stop_overshoot_mm,
        rail_min_mm, rail_max_mm,
    ):
        self.clock = clock
        self.true_position_mm = initial_position_mm
        self.motion_gain = motion_gain
        self.stop_overshoot_mm = stop_overshoot_mm
        self.rail_min_mm = rail_min_mm
        self.rail_max_mm = rail_max_mm
        self.calls = []
        self.moves = []
        self._expected_mm = None
        self._commanded_mm = 0.0
        self._velocity_mm_s = 0.0
        self._last_time = clock()

    def expect_command(self, distance_mm):
        if self._expected_mm is not None:
            raise DrawingError("simulation chassis command overlap")
        distance_mm = _finite(distance_mm, "commanded rail distance")
        direction = 1 if distance_mm > 0 else -1
        predicted = _clean(
            self.true_position_mm
            + distance_mm * self.motion_gain
            + direction * self.stop_overshoot_mm
        )
        if self.rail_min_mm is not None and not (
            self.rail_min_mm <= predicted <= self.rail_max_mm
        ):
            raise DrawingError("simulated true rail move exceeds physical bounds")
        self._expected_mm = distance_mm
        self._commanded_mm = 0.0
        self._velocity_mm_s = 0.0
        self._last_time = self.clock()

    def _integrate(self):
        now = self.clock()
        self._commanded_mm += self._velocity_mm_s * (now - self._last_time)
        self._last_time = now

    def velocity(self, vx_mm_s, vy_mm_s, omega_mrad_s, hold_ms, ttl_ms):
        if vy_mm_s != 0 or omega_mrad_s != 0:
            raise DrawingError("simulation supports rail-axis velocity only")
        if self._expected_mm is None:
            raise DrawingError("production velocity sent without relocation intent")
        self._integrate()
        self._velocity_mm_s = _finite(vx_mm_s, "simulated rail velocity")
        self.calls.append(("velocity", vx_mm_s, hold_ms, ttl_ms))

    def stop(self):
        self._integrate()
        self._velocity_mm_s = 0.0
        self.calls.append(("stop",))
        if self._expected_mm is None:
            return
        commanded = _clean(self._commanded_mm)
        if not math.isclose(commanded, self._expected_mm, abs_tol=1e-6):
            raise DrawingError("production relocation timing changed commanded distance")
        direction = 1 if commanded > 0 else -1
        actual = _clean(
            commanded * self.motion_gain + direction * self.stop_overshoot_mm
        )
        before = self.true_position_mm
        self.true_position_mm = _clean(before + actual)
        refresh_count = sum(call[0] == "velocity" for call in self.calls)
        refresh_count -= sum(move["velocity_refresh_count"] for move in self.moves)
        self.moves.append({
            "expected_commanded_rail_move_mm": _clean(self._expected_mm),
            "timed_commanded_rail_move_mm": commanded,
            "actual_true_rail_move_mm": actual,
            "true_rail_position_before_mm": before,
            "true_rail_position_after_mm": self.true_position_mm,
            "velocity_refresh_count": refresh_count,
        })
        self._expected_mm = None
        self._commanded_mm = 0.0

    def status(self):
        self.calls.append(("status",))
        return {
            "version": 3,
            "sequence": len(self.calls),
            "type": "STATE",
            "ttl_ms": 0,
            "payload": {
                "service_state": "ready",
                "chassis_state": "enabled_stopped",
                "motion_permitted": True,
                "authenticated": True,
                "hold_remaining_ms": 0,
                "last_error": "none",
            },
        }

    def ping(self):
        self.calls.append(("ping",))
        return {"type": "PONG"}


class _SimulationLocalization:
    """Expose true rail position only through deterministic measured locks."""

    def __init__(self, chassis, reference_mm, scale, error_at):
        self.chassis = chassis
        self.measured_reference_mm = _clean(reference_mm + error_at(0))
        self.scale = scale
        self.error_at = error_at
        self.generation = 1
        self.pending_polls = None
        self.calls = []
        self.tasks = []
        self._measure()

    def _measure(self):
        self.error_mm = self.error_at(self.generation)
        self.measured_rail_mm = _clean(
            self.chassis.true_position_mm + self.error_mm
        )
        self.offset_mm = _clean(
            self.scale * (self.measured_rail_mm - self.measured_reference_mm)
        )

    def _locked(self):
        return {
            "state": "locked",
            "generation": self.generation,
            "context": {
                "generation": self.generation,
                "json_axis_offset_mm": self.offset_mm,
                "json_mm_per_rail_mm": self.scale,
                "rail_position_mm": self.measured_rail_mm,
                "source": {"min_confidence": 1.0},
            },
        }

    def snapshot(self):
        self.calls.append("snapshot")
        if self.pending_polls is not None:
            if self.pending_polls > 0:
                self.pending_polls -= 1
                return {
                    "state": "collecting",
                    "generation": self.generation,
                    "context": None,
                }
            self.generation += 1
            self._measure()
            self.pending_polls = None
        return self._locked()

    def begin_task(self, task_id, generation):
        self.tasks.append(("begin", task_id, generation))

    def finish_task(self, task_id, outcome, result):
        self.tasks.append(("finish", task_id, outcome, result))

    def on_motion_intent(self, reason):
        self.calls.append(("motion_intent", reason))

    def on_chassis_status(self, state):
        self.calls.append(("chassis_status", state))

    def request_relocalization(self):
        self.calls.append("request_relocalization")
        self.pending_polls = 1


class _TraceSink:
    def __init__(self, job, config, chassis, localization, scale):
        self.job = job
        self.config = config
        self.chassis = chassis
        self.localization = localization
        self.scale = scale
        self.events = []
        self.windows = []
        self._plans = []

    def __call__(self, event):
        self.events.append(dict(event))
        name = event.get("event") or event.get("state")
        if name == "localized_window_start":
            start = _checkpoint(event.get("checkpoint"))
            plan = build_drawing_plan(
                self.job, self.config, event["json_axis_offset_mm"], start
            )
            self._plans.append(plan)
            measured = self.localization.measured_rail_mm
            self.windows.append({
                "index": event["window"],
                "generation": event["generation"],
                "true_rail_position_mm": _clean(self.chassis.true_position_mm),
                "measured_rail_position_mm": measured,
                "measured_rail_delta_from_reference_mm": _clean(
                    measured - self.localization.measured_reference_mm
                ),
                "localization_error_mm": self.localization.error_mm,
                "json_axis_offset_mm": _clean(event["json_axis_offset_mm"]),
                "checkpoint_start": event.get("checkpoint"),
                "checkpoint_end": (
                    None if plan.next_checkpoint is None
                    else plan.next_checkpoint.to_dict()
                ),
                "point_rank_start": _point_rank(self.job, start),
                "point_rank_end_exclusive": (
                    self.job.point_count if plan.complete
                    else _point_rank(self.job, plan.next_checkpoint)
                ),
                "complete": plan.complete,
                "statistics": dict(plan.statistics),
                "relocation": None,
            })
        elif name == "localized_baseline_start":
            self.chassis.expect_command(event["commanded_rail_distance_mm"])
            plan = self._plans[-1]
            barrier = plan.steps[-1]
            self.windows[-1]["relocation"] = {
                "requested_json_axis_offset_delta_mm": _clean(
                    event["commanded_rail_distance_mm"] * self.scale
                ),
                "required_delta_range_mm": list(
                    barrier.payload["required_json_axis_offset_delta_range_mm"]
                ),
                "commanded_open_loop_rail_move_mm": _clean(
                    event["commanded_rail_distance_mm"]
                ),
                "sequence": _safety_sequence(plan) + [
                    "chassis_direct_move", "stop", "enabled_stopped", "settle",
                    "apriltag_lock_new_generation", "resume_checkpoint",
                ],
            }
        elif name == "localized_relocation_done":
            move = self.chassis.moves[-1]
            relocation = self.windows[-1]["relocation"]
            relocation.update({
                "timed_commanded_rail_move_mm": move[
                    "timed_commanded_rail_move_mm"
                ],
                "actual_true_rail_move_mm": move["actual_true_rail_move_mm"],
                "true_rail_position_after_mm": move[
                    "true_rail_position_after_mm"
                ],
                "localization_error_after_mm": self.localization.error_mm,
                "measured_rail_position_after_mm": event[
                    "measured_rail_position_mm"
                ],
                "logical_stop_state": "enabled_stopped",
                "generation_after": event["localization_generation"],
                "measured_json_axis_offset_after_mm": event[
                    "json_axis_offset_mm"
                ],
                "production_reported_json_axis_offset_delta_mm": event[
                    "json_axis_offset_delta_mm"
                ],
                "velocity_refresh_count": move["velocity_refresh_count"],
            })


def _result(
    job, source_config, simulation_config, control_config, trace, arm, chassis,
    localization, true_reference_mm, initial_true_mm, initial_measured_mm,
    motion_gain, stop_overshoot_mm, localization_errors_mm, rail_min_mm,
    rail_max_mm, coordinator_result,
):
    geometry = simulation_config.geometry
    relocations = [
        window["relocation"] for window in trace.windows
        if window["relocation"] is not None
    ]
    commanded_moves = [
        item["commanded_open_loop_rail_move_mm"] for item in relocations
    ]
    actual_moves = [item["actual_true_rail_move_mm"] for item in relocations]
    directions = [1 if value > 0 else -1 for value in actual_moves if value]
    direction_changes = sum(
        directions[index] != directions[index - 1]
        for index in range(1, len(directions))
    )
    warnings = []
    if direction_changes:
        warnings.append("simulated_rail_direction_reversal")
    if motion_gain != 1 or stop_overshoot_mm != 0:
        warnings.append("open_loop_motion_error_enabled")
    if any(value != localization_errors_mm[0] for value in localization_errors_mm[1:]):
        warnings.append("varying_localization_error_enabled")
    return {
        "schema": "localized-baseline-rehearsal/3",
        "simulation_only": True,
        "mode": "localized_baseline",
        "production_path": {
            "coordinator": "drawing.coordinator.execute_drawing",
            "relocator": "drawing.control_modes.LocalizedBaselineRelocator",
            "window_executor": "drawing.executor.execute_drawing_window",
            "velocity_calls": sum(call[0] == "velocity" for call in chassis.calls),
            "stop_calls": sum(call[0] == "stop" for call in chassis.calls),
            "status_calls": sum(call[0] == "status" for call in chassis.calls),
            "relocalization_requests": localization.calls.count(
                "request_relocalization"
            ),
            "queued_stroke_calls": arm.calls.count("draw_stroke"),
            "direct_arm_motion_calls": sum(
                call in ("move_joint", "jog_xyz", "gripper")
                for call in arm.calls
            ),
            "arm_motion_calls": sum(
                call in ("move_joint", "jog_xyz", "draw_stroke", "gripper")
                for call in arm.calls
            ),
        },
        "assumptions": [
            "one_dimensional_translation_only",
            "fixed_motion_gain_and_stop_overshoot",
            "predetermined_apriltag_measurement_errors",
            "no_yaw_or_lateral_motion",
            "no_tag_dropout_or_network_latency",
            "enabled_stopped_is_logical_not_measured_physical_stop",
        ],
        "calibration": {
            "true_rail_reference_mm": true_reference_mm,
            "measured_rail_reference_mm": localization.measured_reference_mm,
            "initial_true_rail_position_mm": initial_true_mm,
            "initial_measured_rail_position_mm": initial_measured_mm,
            "json_mm_per_rail_mm": control_config.json_mm_per_rail_mm,
            "formula": (
                "json_axis_offset_mm = scale * "
                "(measured_rail_mm - measured_reference_mm)"
            ),
        },
        "physical_model": {
            "motion_gain": motion_gain,
            "stop_overshoot_mm": stop_overshoot_mm,
            "localization_errors_mm": list(localization_errors_mm),
            "rail_min_mm": rail_min_mm,
            "rail_max_mm": rail_max_mm,
            "move_formula": (
                "actual_move = timed_velocity_integral * motion_gain + "
                "sign(commanded_move) * stop_overshoot_mm"
            ),
        },
        "control": {
            "speed_mm_s": control_config.baseline.speed_mm_s,
            "refresh_ms": control_config.baseline.refresh_ms,
            "hold_ms": control_config.baseline.hold_ms,
            "max_distance_mm": control_config.baseline.max_distance_mm,
            "localization_poll_ms": control_config.localized_baseline.poll_ms,
            "localization_timeout_ms": (
                control_config.localized_baseline.localization_timeout_ms
            ),
        },
        "geometry": {
            "canvas_width_mm": geometry.canvas_width_mm,
            "canvas_height_mm": geometry.canvas_height_mm,
            "canvas_top_left_from_home_mm": list(geometry.canvas_top_left_from_home_mm),
            "canvas_u_vector_from_home_mm": list(geometry.canvas_u_vector_from_home_mm),
            "canvas_v_vector_from_home_mm": list(geometry.canvas_v_vector_from_home_mm),
            "rail_offset_vector_from_home_mm_per_json_mm": list(
                geometry.rail_offset_vector_from_home_mm_per_json_mm
            ),
            "reachable_home_relative_y_min_mm": geometry.reachable_home_relative_y_min_mm,
            "reachable_home_relative_y_max_mm": geometry.reachable_home_relative_y_max_mm,
            "pen_down_delta_from_lift_mm": list(geometry.pen_down_delta_from_lift_mm),
            "user": geometry.user,
            "tool": geometry.tool,
        },
        "drawing": canonical_document(job),
        "job_sha256": job.canonical_sha256,
        "source_config_sha256": source_config.canonical_sha256,
        "source_config_reach_overridden": (
            geometry.reachable_home_relative_y_min_mm
            != source_config.geometry.reachable_home_relative_y_min_mm
            or geometry.reachable_home_relative_y_max_mm
            != source_config.geometry.reachable_home_relative_y_max_mm
        ),
        "windows": trace.windows,
        "summary": {
            "outcome": "complete",
            "groups": len(job.groups),
            "strokes": job.stroke_count,
            "points": job.point_count,
            "windows": coordinator_result["windows"],
            "relocations": len(relocations),
            "final_generation": coordinator_result["final_generation"],
            "final_true_rail_position_mm": _clean(chassis.true_position_mm),
            "final_measured_rail_position_mm": localization.measured_rail_mm,
            "final_json_axis_offset_mm": coordinator_result[
                "final_json_axis_offset_mm"
            ],
            "total_absolute_commanded_rail_travel_mm": _clean(
                sum(abs(value) for value in commanded_moves)
            ),
            "total_absolute_rail_travel_mm": _clean(
                sum(abs(value) for value in actual_moves)
            ),
            "rail_direction_changes": direction_changes,
            "scenario_warnings": warnings,
        },
    }


def simulate_localized_baseline(
    job,
    config,
    control_config=None,
    rail_reference_mm=0.0,
    initial_rail_position_mm=None,
    json_mm_per_rail_mm=None,
    reachable_min_mm=None,
    reachable_max_mm=None,
    motion_gain=1.0,
    stop_overshoot_mm=0.0,
    localization_errors_mm=(0.0,),
    rail_min_mm=None,
    rail_max_mm=None,
    max_windows=100,
):
    """Execute production orchestration against deterministic fake devices."""
    true_reference_mm = _finite(rail_reference_mm, "rail_reference_mm")
    if initial_rail_position_mm is None:
        initial_rail_position_mm = true_reference_mm
    initial_true_mm = _finite(initial_rail_position_mm, "initial_rail_position_mm")
    if json_mm_per_rail_mm is not None:
        json_mm_per_rail_mm = _finite(
            json_mm_per_rail_mm, "json_mm_per_rail_mm"
        )
        if json_mm_per_rail_mm == 0:
            raise DrawingError("json_mm_per_rail_mm must not be zero")
    if isinstance(max_windows, bool) or not isinstance(max_windows, int) or max_windows < 1:
        raise DrawingError("max_windows must be a positive integer")
    motion_gain = _finite(motion_gain, "motion_gain")
    stop_overshoot_mm = _finite(stop_overshoot_mm, "stop_overshoot_mm")
    if motion_gain < 0:
        raise DrawingError("motion_gain must not be negative")
    if stop_overshoot_mm < 0:
        raise DrawingError("stop_overshoot_mm must not be negative")
    if not isinstance(localization_errors_mm, (tuple, list)) or not localization_errors_mm:
        raise DrawingError("localization_errors_mm must contain at least one value")
    localization_errors_mm = tuple(
        _finite(value, "localization_errors_mm")
        for value in localization_errors_mm
    )
    rail_min_mm = None if rail_min_mm is None else _finite(rail_min_mm, "rail_min_mm")
    rail_max_mm = None if rail_max_mm is None else _finite(rail_max_mm, "rail_max_mm")
    if (rail_min_mm is None) != (rail_max_mm is None):
        raise DrawingError("rail_min_mm and rail_max_mm must be supplied together")
    if rail_min_mm is not None and rail_min_mm >= rail_max_mm:
        raise DrawingError("rail minimum must be below maximum")
    if rail_min_mm is not None and not rail_min_mm <= initial_true_mm <= rail_max_mm:
        raise DrawingError("initial true rail position is outside physical bounds")

    def error_at(lock_index):
        if len(localization_errors_mm) == 1:
            return localization_errors_mm[0]
        if lock_index >= len(localization_errors_mm):
            raise DrawingError("localization error sequence exhausted")
        return localization_errors_mm[lock_index]

    drawing_config = _simulation_drawing_config(
        config, reachable_min_mm, reachable_max_mm
    )
    control_config = _simulation_control_config(
        control_config, json_mm_per_rail_mm
    )
    scale = control_config.json_mm_per_rail_mm
    clock = _SimulationClock()
    chassis = _SimulationChassis(
        clock, initial_true_mm, motion_gain, stop_overshoot_mm,
        rail_min_mm, rail_max_mm,
    )
    localization = _SimulationLocalization(
        chassis, true_reference_mm, scale, error_at
    )
    initial_measured_mm = localization.measured_rail_mm
    arm = _SimulationArm()
    trace = _TraceSink(job, drawing_config, chassis, localization, scale)
    result = execute_drawing(
        arm,
        chassis,
        localization,
        job,
        drawing_config,
        control_config,
        DrawingExecutionAdmission(True, True, True, True),
        RelocationAdmission(True, True, True, "enabled_stopped"),
        task_id="simulation-%s" % job.canonical_sha256[:16],
        event_sink=trace,
        sleep_func=clock.sleep,
        clock=clock,
        max_windows=max_windows,
    )
    return _result(
        job, config, drawing_config, control_config, trace, arm, chassis,
        localization, true_reference_mm, initial_true_mm, initial_measured_mm,
        motion_gain, stop_overshoot_mm, localization_errors_mm, rail_min_mm,
        rail_max_mm, result,
    )
