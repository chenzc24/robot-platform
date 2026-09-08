"""Fail-closed one-dimensional rail localization with reusable task context."""

import math
import threading
import time
from collections import deque
from copy import deepcopy


class LocalizationStateError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _finite(value, code):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise LocalizationStateError(code)
    return float(value)


def _pose_matrix(value):
    """Validate enough of a homogeneous pose to safely read its translation."""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise LocalizationStateError("vision_transform_invalid")
    if any(not isinstance(row, (list, tuple)) or len(row) != 4 for row in value):
        raise LocalizationStateError("vision_transform_invalid")
    matrix = tuple(tuple(_finite(axis, "vision_transform_invalid") for axis in row) for row in value)
    if any(abs(matrix[3][index]) > 1e-9 for index in range(3)) or abs(matrix[3][3] - 1.0) > 1e-9:
        raise LocalizationStateError("vision_transform_invalid")
    return matrix


class RailLocalizationStateMachine:
    """Lock the camera's scalar rail position after stopped, stable vision."""

    TERMINAL_TASK_STATES = {"DONE", "FAULT", "REJECTED", "UNKNOWN"}
    RAIL_AXES = {"x": 0, "y": 1, "z": 2}
    JSON_AXES = {"x", "y"}

    def __init__(
        self,
        *,
        enabled,
        rail_axis="x",
        json_axis="x",
        json_origin_rail_position_mm=0.0,
        json_mm_per_rail_mm=-1.0,
        configuration_error=None,
        settle_time_ms=2000,
        sample_window_ms=3000,
        min_valid_samples=8,
        min_visible_tags=2,
        max_position_spread_mm=2.0,
        clock=None,
    ):
        self.enabled = enabled is True
        self.rail_axis = rail_axis
        self.json_axis = json_axis
        self.json_origin_rail_position_mm = float(json_origin_rail_position_mm)
        self.json_mm_per_rail_mm = float(json_mm_per_rail_mm)
        self.configuration_error = configuration_error or self._configuration_error()
        self.settle_time_ms = int(settle_time_ms)
        self.sample_window_ms = int(sample_window_ms)
        self.min_valid_samples = int(min_valid_samples)
        self.min_visible_tags = int(min_visible_tags)
        self.max_position_spread_mm = float(max_position_spread_mm)
        self._clock = clock or time.monotonic
        self._lock = threading.RLock()
        self._samples = deque()
        self._generation = 0
        self._revision = 0
        self._chassis_state = "unknown"
        self._settle_until = None
        self._locked_context = None
        self._active_task = None
        self._last_task = None
        self._last_observation_error = "none"
        if not self.enabled:
            self._state, self._reason = "disabled", "localization_disabled"
        elif self.configuration_error:
            self._state, self._reason = "blocked", str(self.configuration_error)
        else:
            self._state, self._reason = "invalid", "startup"

    def _configuration_error(self):
        if self.rail_axis not in self.RAIL_AXES:
            return "invalid_rail_axis"
        if self.json_axis not in self.JSON_AXES:
            return "invalid_json_axis"
        if not math.isfinite(self.json_origin_rail_position_mm):
            return "invalid_json_origin_rail_position"
        if not math.isfinite(self.json_mm_per_rail_mm) or self.json_mm_per_rail_mm == 0:
            return "invalid_json_rail_scale"
        return None

    def _now(self, now=None):
        value = self._clock() if now is None else now
        return _finite(value, "invalid_localization_time")

    def _touch(self):
        self._revision += 1

    def _mark_active_task_unknown(self, reason):
        if self._active_task is None:
            return
        self._last_task = {**self._active_task, "state": "UNKNOWN", "result": reason}
        self._active_task = None

    def _invalidate(self, reason, state="invalid"):
        self._mark_active_task_unknown(reason)
        self._samples.clear()
        self._settle_until = None
        self._locked_context = None
        self._state, self._reason = state, str(reason)
        self._last_observation_error = "none"
        self._touch()

    def _begin_settling(self, now, reason):
        self._mark_active_task_unknown(reason)
        self._samples.clear()
        self._locked_context = None
        self._settle_until = now + self.settle_time_ms / 1000.0
        self._state, self._reason = "settling", reason
        self._last_observation_error = "none"
        self._touch()

    def on_motion_intent(self, reason="chassis_motion_intent"):
        with self._lock:
            if not self.enabled:
                return
            self._chassis_state = "moving"
            if self._state != "blocked":
                self._invalidate(reason, "moving")

    def on_chassis_unavailable(self, reason="chassis_unavailable"):
        with self._lock:
            if not self.enabled:
                return
            self._chassis_state = "unknown"
            if self._state != "blocked":
                self._invalidate(reason)

    def on_chassis_status(self, state, now=None):
        now = self._now(now)
        if not isinstance(state, str) or not state:
            raise LocalizationStateError("invalid_chassis_state")
        with self._lock:
            previous = self._chassis_state
            self._chassis_state = state
            if not self.enabled or self._state == "blocked":
                return
            if state == "moving":
                self._invalidate("chassis_moving", "moving")
            elif state == "enabled_stopped":
                if previous != "enabled_stopped" or self._state in {"invalid", "moving"}:
                    self._begin_settling(now, "chassis_logically_stopped")
            else:
                self._invalidate("chassis_not_confirmed_stopped")

    def request_relocalization(self, now=None):
        now = self._now(now)
        with self._lock:
            if not self.enabled:
                raise LocalizationStateError("localization_disabled")
            if self._state == "blocked":
                raise LocalizationStateError(self._reason)
            if self._active_task is not None:
                raise LocalizationStateError("localized_task_running")
            if self._chassis_state != "enabled_stopped":
                raise LocalizationStateError("chassis_not_confirmed_stopped")
            self._begin_settling(now, "relocalization_requested")

    def _tick_locked(self, now):
        if self._state == "settling" and self._settle_until is not None and now >= self._settle_until:
            self._settle_until = None
            self._state, self._reason = "collecting", "waiting_for_stable_vision"
            self._samples.clear()
            self._touch()
        if self._state == "collecting":
            cutoff = now - self.sample_window_ms / 1000.0
            previous_count = len(self._samples)
            while self._samples and self._samples[0]["received_at"] < cutoff:
                self._samples.popleft()
            if len(self._samples) != previous_count:
                self._touch()

    def tick(self, now=None):
        now = self._now(now)
        with self._lock:
            self._tick_locked(now)

    @staticmethod
    def _numeric(value, default):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return default
        return float(value)

    def observe_vision(self, result, now=None):
        now = self._now(now)
        with self._lock:
            self._tick_locked(now)
            if self._state != "collecting":
                return
            if not isinstance(result, dict) or not result.get("accepted") or not result.get("pose_solved"):
                self._last_observation_error = (
                    str(result.get("error", "vision_result_not_accepted"))
                    if isinstance(result, dict) else "vision_result_invalid"
                )
                self._touch()
                return
            if result.get("camera_calibration_ready") is not True or result.get("board_layout_ready") is not True:
                self._last_observation_error = "vision_calibration_unverified"
                self._touch()
                return
            raw_ids = result.get("used_ids")
            if not isinstance(raw_ids, list) or any(
                    isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in raw_ids):
                self._last_observation_error = "vision_used_ids_invalid"
                self._touch()
                return
            used_ids = sorted(set(raw_ids))
            if len(used_ids) < self.min_visible_tags:
                self._last_observation_error = "insufficient_visible_tags"
                self._touch()
                return
            try:
                transform = _pose_matrix(result.get("T_board_from_camera"))
            except LocalizationStateError as error:
                self._last_observation_error = error.code
                self._touch()
                return
            source_values = tuple(result.get(key) for key in ("calibration_id", "layout_id", "board_frame"))
            if not all(isinstance(value, str) and value.strip() for value in source_values):
                self._last_observation_error = "vision_source_id_missing"
                self._touch()
                return
            source_key = tuple(value.strip() for value in source_values)
            if self._samples and self._samples[-1]["source_key"] != source_key:
                self._samples.clear()
            frame_sequence = result.get("frame_sequence")
            captured_at_ms = result.get("captured_at_ms")
            if (isinstance(frame_sequence, bool) or not isinstance(frame_sequence, int) or frame_sequence < 1
                    or isinstance(captured_at_ms, bool) or not isinstance(captured_at_ms, int)
                    or captured_at_ms < 0):
                self._last_observation_error = "vision_frame_identity_invalid"
                self._touch()
                return
            if self._samples and frame_sequence <= self._samples[-1]["frame_sequence"]:
                self._last_observation_error = "vision_frame_not_new"
                self._touch()
                return
            confidence = self._numeric(result.get("confidence"), None)
            rmse = self._numeric(result.get("reprojection_rmse_px"), None)
            if confidence is None or rmse is None or not 0.0 <= confidence <= 1.0 or rmse < 0.0:
                self._last_observation_error = "vision_quality_invalid"
                self._touch()
                return
            position = transform[self.RAIL_AXES[self.rail_axis]][3]
            self._samples.append({
                "received_at": now,
                "position_mm": position,
                "source_key": source_key,
                "frame_sequence": frame_sequence,
                "captured_at_ms": captured_at_ms,
                "used_ids": used_ids,
                "confidence": confidence,
                "rmse": rmse,
            })
            self._reason = "waiting_for_stable_vision"
            self._last_observation_error = "none"
            if len(self._samples) < self.min_valid_samples:
                self._touch()
                return
            rail_position = sum(item["position_mm"] for item in self._samples) / len(self._samples)
            position_spread = max(abs(item["position_mm"] - rail_position) for item in self._samples)
            if position_spread > self.max_position_spread_mm:
                self._reason = "rail_position_unstable"
                self._touch()
                return
            rail_delta = rail_position - self.json_origin_rail_position_mm
            json_offset = self.json_mm_per_rail_mm * rail_delta
            all_ids = sorted({tag_id for item in self._samples for tag_id in item["used_ids"]})
            self._generation += 1
            self._locked_context = {
                "generation": self._generation,
                "mode": "rail_1d",
                "board_frame": self._samples[-1]["source_key"][2],
                "rail_axis": self.rail_axis,
                "json_axis": self.json_axis,
                "rail_position_mm": round(rail_position, 6),
                "json_origin_rail_position_mm": round(self.json_origin_rail_position_mm, 6),
                "rail_delta_from_json_origin_mm": round(rail_delta, 6),
                "json_mm_per_rail_mm": round(self.json_mm_per_rail_mm, 9),
                "json_axis_offset_mm": round(json_offset, 6),
                "source": {
                    "calibration_id": self._samples[-1]["source_key"][0],
                    "layout_id": self._samples[-1]["source_key"][1],
                    "sample_count": len(self._samples),
                    "first_frame_sequence": self._samples[0]["frame_sequence"],
                    "last_frame_sequence": self._samples[-1]["frame_sequence"],
                    "first_captured_at_ms": self._samples[0]["captured_at_ms"],
                    "last_captured_at_ms": self._samples[-1]["captured_at_ms"],
                    "used_ids": all_ids,
                    "min_confidence": round(min(item["confidence"] for item in self._samples), 6),
                    "max_reprojection_rmse_px": round(max(item["rmse"] for item in self._samples), 6),
                    "position_spread_mm": round(position_spread, 6),
                },
            }
            self._state, self._reason = "locked", "stable_rail_position_locked"
            self._samples.clear()
            self._touch()

    @staticmethod
    def _task_id(value):
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 80:
            raise LocalizationStateError("invalid_task_id")
        return value.strip()

    def task_context(self, expected_generation=None):
        with self._lock:
            if self._state != "locked" or self._locked_context is None:
                raise LocalizationStateError("localization_not_locked")
            if expected_generation is not None and (
                    isinstance(expected_generation, bool) or not isinstance(expected_generation, int)
                    or expected_generation <= 0):
                raise LocalizationStateError("invalid_localization_generation")
            if expected_generation is not None and expected_generation != self._generation:
                raise LocalizationStateError("stale_localization_generation")
            return deepcopy(self._locked_context)

    def begin_task(self, task_id, expected_generation=None):
        task_id = self._task_id(task_id)
        with self._lock:
            context = self.task_context(expected_generation)
            if self._active_task is not None:
                raise LocalizationStateError("localized_task_running")
            self._active_task = {
                "task_id": task_id,
                "generation": self._generation,
                "state": "RUNNING",
                "result": "none",
            }
            self._touch()
            return context

    def finish_task(self, task_id, outcome, result="none"):
        task_id = self._task_id(task_id)
        if outcome not in self.TERMINAL_TASK_STATES:
            raise LocalizationStateError("invalid_task_outcome")
        with self._lock:
            if self._active_task is None or self._active_task["task_id"] != task_id:
                raise LocalizationStateError("localized_task_not_active")
            self._last_task = {**self._active_task, "state": outcome, "result": str(result)[:160]}
            self._active_task = None
            self._touch()

    def snapshot(self, now=None):
        now = self._now(now)
        with self._lock:
            self._tick_locked(now)
            remaining = None if self._settle_until is None else max(0, int((self._settle_until - now) * 1000))
            return {
                "enabled": self.enabled,
                "state": self._state,
                "reason": self._reason,
                "revision": self._revision,
                "valid": self._state == "locked" and self._locked_context is not None,
                "generation": self._generation,
                "chassis_state": self._chassis_state,
                "rail_axis": self.rail_axis,
                "json_axis": self.json_axis,
                "json_origin_rail_position_mm": self.json_origin_rail_position_mm,
                "json_mm_per_rail_mm": self.json_mm_per_rail_mm,
                "max_position_spread_mm": self.max_position_spread_mm,
                "settling_remaining_ms": remaining,
                "sample_count": len(self._samples),
                "min_valid_samples": self.min_valid_samples,
                "last_observation_error": self._last_observation_error,
                "context": deepcopy(self._locked_context),
                "task": {"active": deepcopy(self._active_task), "last": deepcopy(self._last_task)},
            }
