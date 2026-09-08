"""Explicit baseline and advanced relocation strategies for drawing tasks."""

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

from .models import DrawingError


_TOP_FIELDS = {"version", "production_ready", "selected_mode", "json_mm_per_rail_mm", "baseline", "advanced"}
_BASELINE_FIELDS = {"speed_mm_s", "refresh_ms", "hold_ms", "max_distance_mm", "settle_ms"}
_ADVANCED_FIELDS = {"poll_ms", "station_timeout_ms", "localization_timeout_ms"}


def _number(value, label, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DrawingError("%s must be a finite number" % label)
    value = float(value)
    if not math.isfinite(value):
        raise DrawingError("%s must be a finite number" % label)
    if minimum is not None and value < minimum:
        raise DrawingError("%s is below its minimum" % label)
    if maximum is not None and value > maximum:
        raise DrawingError("%s exceeds its maximum" % label)
    return value


def _integer(value, label, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int):
        raise DrawingError("%s must be an integer" % label)
    if not minimum <= value <= maximum:
        raise DrawingError("%s is outside its allowed range" % label)
    return value


def _exact(document, fields, label):
    if not isinstance(document, dict) or set(document) != set(fields):
        raise DrawingError("%s has unexpected or missing fields" % label)


@dataclass(frozen=True)
class BaselineRelocationConfig:
    speed_mm_s: int
    refresh_ms: int
    hold_ms: int
    max_distance_mm: float
    settle_ms: int


@dataclass(frozen=True)
class AdvancedRelocationConfig:
    poll_ms: int
    station_timeout_ms: int
    localization_timeout_ms: int


@dataclass(frozen=True)
class DrawingControlConfig:
    production_ready: bool
    selected_mode: str
    json_mm_per_rail_mm: float
    baseline: BaselineRelocationConfig
    advanced: AdvancedRelocationConfig


@dataclass(frozen=True)
class RelocationAdmission:
    attended: bool
    emergency_stop_ready: bool
    arm_safe: bool
    chassis_state: str

    def validate(self):
        if not self.attended:
            raise DrawingError("relocation_requires_attended_operator")
        if not self.emergency_stop_ready:
            raise DrawingError("relocation_requires_emergency_stop")
        if not self.arm_safe:
            raise DrawingError("relocation_requires_arm_safe")
        if self.chassis_state != "enabled_stopped":
            raise DrawingError("relocation_requires_enabled_stopped")


@dataclass(frozen=True)
class RelocationResult:
    mode: str
    offset_source: str
    json_axis_offset_mm: float
    json_axis_offset_delta_mm: float
    commanded_rail_distance_mm: object
    measured_rail_position_mm: object
    localization_generation: object
    confidence: object

    def to_dict(self):
        return dict(self.__dict__)


def parse_drawing_control_config(document):
    _exact(document, _TOP_FIELDS, "drawing control config")
    if document["version"] != 1 or isinstance(document["version"], bool):
        raise DrawingError("drawing control version must be 1")
    if type(document["production_ready"]) is not bool:
        raise DrawingError("production_ready must be boolean")
    mode = document["selected_mode"]
    if mode not in ("baseline", "advanced"):
        raise DrawingError("selected_mode must be baseline or advanced")
    scale = _number(document["json_mm_per_rail_mm"], "json_mm_per_rail_mm", -10.0, 10.0)
    if scale == 0:
        raise DrawingError("json_mm_per_rail_mm must not be zero")

    baseline = document["baseline"]
    _exact(baseline, _BASELINE_FIELDS, "baseline")
    baseline_config = BaselineRelocationConfig(
        speed_mm_s=_integer(baseline["speed_mm_s"], "baseline.speed_mm_s", 1, 600),
        refresh_ms=_integer(baseline["refresh_ms"], "baseline.refresh_ms", 20, 400),
        hold_ms=_integer(baseline["hold_ms"], "baseline.hold_ms", 100, 500),
        max_distance_mm=_number(baseline["max_distance_mm"], "baseline.max_distance_mm", 1.0, 2000.0),
        settle_ms=_integer(baseline["settle_ms"], "baseline.settle_ms", 0, 10000),
    )
    if baseline_config.refresh_ms >= baseline_config.hold_ms:
        raise DrawingError("baseline.refresh_ms must be less than hold_ms")

    advanced = document["advanced"]
    _exact(advanced, _ADVANCED_FIELDS, "advanced")
    advanced_config = AdvancedRelocationConfig(
        poll_ms=_integer(advanced["poll_ms"], "advanced.poll_ms", 20, 1000),
        station_timeout_ms=_integer(advanced["station_timeout_ms"], "advanced.station_timeout_ms", 100, 120000),
        localization_timeout_ms=_integer(advanced["localization_timeout_ms"], "advanced.localization_timeout_ms", 100, 120000),
    )
    return DrawingControlConfig(document["production_ready"], mode, scale, baseline_config, advanced_config)


def load_drawing_control_config(path):
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DrawingError("cannot read drawing control config: %s" % type(error).__name__)
    return parse_drawing_control_config(document)


class _Relocator:
    def __init__(self, config, clock=None, sleep=None, event=None):
        self.config = config
        self.clock = clock or time.monotonic
        self.sleep = sleep or time.sleep
        self.event = event or (lambda _record: None)

    def _admit(self, admission):
        if not isinstance(admission, RelocationAdmission):
            raise DrawingError("relocation admission is required")
        admission.validate()
        if not self.config.production_ready:
            raise DrawingError("drawing_control_not_production_ready")

    def _rail_distance(self, json_delta_mm):
        json_delta_mm = _number(json_delta_mm, "json offset delta")
        if json_delta_mm == 0:
            raise DrawingError("json offset delta must not be zero")
        return json_delta_mm / self.config.json_mm_per_rail_mm

    def _emit(self, state, **details):
        self.event({"state": state, **details})


class BaselineRelocator(_Relocator):
    """Trust configured speed and elapsed time; never claim measured travel."""

    def __init__(self, chassis, config, **kwargs):
        super().__init__(config, **kwargs)
        self.chassis = chassis

    def relocate(self, offset_before_mm, json_delta_mm, admission):
        self._admit(admission)
        offset_before_mm = _number(offset_before_mm, "offset_before_mm")
        rail_distance = self._rail_distance(json_delta_mm)
        settings = self.config.baseline
        if abs(rail_distance) > settings.max_distance_mm:
            raise DrawingError("baseline_distance_exceeds_limit")
        direction = 1 if rail_distance > 0 else -1
        deadline = self.clock() + abs(rail_distance) / settings.speed_mm_s
        refresh_count = 0
        motion_error = None
        self._emit("baseline_start", commanded_rail_distance_mm=rail_distance, speed_mm_s=direction * settings.speed_mm_s)
        try:
            while self.clock() < deadline:
                self.chassis.velocity(direction * settings.speed_mm_s, 0, 0, settings.hold_ms, max(500, settings.hold_ms))
                refresh_count += 1
                remaining = max(0.0, deadline - self.clock())
                self.sleep(min(settings.refresh_ms / 1000.0, remaining))
        except Exception as error:
            motion_error = error
        try:
            self.chassis.stop()
        except Exception as error:
            raise DrawingError("baseline_stop_unconfirmed") from error
        if motion_error is not None:
            raise DrawingError("baseline_motion_failed") from motion_error
        self.sleep(settings.settle_ms / 1000.0)
        new_offset = offset_before_mm + json_delta_mm
        self._emit("baseline_done", commanded_rail_distance_mm=rail_distance, refresh_count=refresh_count, json_axis_offset_mm=new_offset)
        return RelocationResult("baseline", "commanded_open_loop", round(new_offset, 6), round(json_delta_mm, 6), round(rail_distance, 6), None, None, None)


class AdvancedRelocator(_Relocator):
    """Follow locally to one station, then require a fresh AprilTag lock."""

    def __init__(self, chassis, localization, config, **kwargs):
        super().__init__(config, **kwargs)
        self.chassis = chassis
        self.localization = localization

    @staticmethod
    def _payload(message):
        if not isinstance(message, dict) or not isinstance(message.get("payload"), dict):
            raise DrawingError("invalid_line_follow_response")
        return message["payload"]

    def relocate(self, offset_before_mm, json_delta_mm, admission):
        self._admit(admission)
        offset_before_mm = _number(offset_before_mm, "offset_before_mm")
        rail_distance = self._rail_distance(json_delta_mm)
        direction = 1 if rail_distance > 0 else -1
        settings = self.config.advanced
        before = self.localization.snapshot()
        old_generation = before.get("generation", 0)
        before_context = before.get("context") or {}
        if "json_mm_per_rail_mm" in before_context:
            before_scale = _number(
                before_context["json_mm_per_rail_mm"],
                "localized json_mm_per_rail_mm",
            )
            if before_scale != self.config.json_mm_per_rail_mm:
                raise DrawingError("advanced_localization_scale_mismatch")
        station_deadline = self.clock() + settings.station_timeout_ms / 1000.0
        station_confirmed = False
        self._emit("advanced_line_follow_start", direction=direction)
        try:
            self.chassis.line_follow_start(direction)
            while self.clock() < station_deadline:
                state = self._payload(self.chassis.line_follow_status())
                if state.get("state") == "station":
                    station_confirmed = True
                    break
                if state.get("state") in ("fault", "idle"):
                    raise DrawingError("advanced_line_follow_%s" % state.get("state"))
                self.sleep(settings.poll_ms / 1000.0)
        finally:
            try:
                self.chassis.line_follow_stop()
            except Exception as error:
                raise DrawingError("advanced_line_follow_stop_unconfirmed") from error
        if not station_confirmed:
            raise DrawingError("advanced_station_timeout")

        self.localization.request_relocalization()
        lock_deadline = self.clock() + settings.localization_timeout_ms / 1000.0
        self._emit("advanced_localization_start", previous_generation=old_generation)
        while self.clock() < lock_deadline:
            self.chassis.ping()
            snapshot = self.localization.snapshot()
            if snapshot.get("state") == "locked" and snapshot.get("generation", 0) > old_generation:
                context = snapshot.get("context") or {}
                source = context.get("source") or {}
                locked_scale = _number(
                    context.get("json_mm_per_rail_mm"),
                    "localized json_mm_per_rail_mm",
                )
                if locked_scale != self.config.json_mm_per_rail_mm:
                    raise DrawingError("advanced_localization_scale_mismatch")
                new_offset = _number(context.get("json_axis_offset_mm"), "localized json offset")
                self._emit("advanced_done", generation=context.get("generation"), json_axis_offset_mm=new_offset)
                return RelocationResult("advanced", "apriltag_locked", round(new_offset, 6), round(new_offset - offset_before_mm, 6), None, context.get("rail_position_mm"), context.get("generation"), source.get("min_confidence"))
            if snapshot.get("state") in ("blocked", "invalid", "disabled"):
                raise DrawingError("advanced_localization_%s" % snapshot.get("state"))
            self.sleep(settings.poll_ms / 1000.0)
        raise DrawingError("advanced_localization_timeout")


def create_relocator(config, chassis, localization=None, **kwargs):
    if config.selected_mode == "baseline":
        return BaselineRelocator(chassis, config, **kwargs)
    if localization is None:
        raise DrawingError("advanced_mode_requires_localization")
    return AdvancedRelocator(chassis, localization, config, **kwargs)


def relocate_reposition_plan(plan, relocator, admission):
    """Consume one planner barrier and return the exact resume context."""
    if plan.complete or plan.next_checkpoint is None or not plan.steps:
        raise DrawingError("drawing_plan_has_no_reposition_barrier")
    barrier = plan.steps[-1]
    if barrier.kind != "reposition.required":
        raise DrawingError("drawing_plan_has_no_reposition_barrier")
    delta = barrier.payload.get("suggested_json_axis_offset_delta_mm")
    result = relocator.relocate(
        plan.json_axis_offset_mm,
        delta,
        admission,
    )
    return {
        "checkpoint": plan.next_checkpoint.to_dict(),
        "json_axis_offset_mm": result.json_axis_offset_mm,
        "relocation": result.to_dict(),
    }
