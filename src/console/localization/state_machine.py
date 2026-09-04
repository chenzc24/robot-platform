"""Fail-closed localization locking with a reusable task context."""

import math
import threading
import time
from collections import deque
from copy import deepcopy

from .geometry import GeometryError, average_transforms, compose, inverse, rigid_transform, transform_list


class LocalizationStateError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class LocalizationLockStateMachine:
    """Fuse stable stopped-camera poses and freeze one transform generation."""

    TERMINAL_TASK_STATES = {"DONE", "FAULT", "REJECTED", "UNKNOWN"}

    def __init__(
        self,
        *,
        enabled,
        geometry=None,
        configuration_error=None,
        settle_time_ms=2000,
        sample_window_ms=3000,
        min_valid_samples=8,
        min_visible_tags=2,
        max_translation_spread_mm=2.0,
        max_rotation_spread_deg=1.0,
        clock=None,
    ):
        self.enabled = enabled is True
        self.geometry = geometry
        self.configuration_error = configuration_error
        self.settle_time_ms = int(settle_time_ms)
        self.sample_window_ms = int(sample_window_ms)
        self.min_valid_samples = int(min_valid_samples)
        self.min_visible_tags = int(min_visible_tags)
        self.max_translation_spread_mm = float(max_translation_spread_mm)
        self.max_rotation_spread_deg = float(max_rotation_spread_deg)
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
        elif configuration_error:
            self._state, self._reason = "blocked", str(configuration_error)
        elif geometry is None:
            self._state, self._reason = "blocked", "robot_geometry_unavailable"
        elif not geometry.production_ready:
            self._state, self._reason = "blocked", "robot_geometry_unverified"
        else:
            self._state, self._reason = "invalid", "startup"

    def _now(self, now=None):
        value = self._clock() if now is None else now
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise LocalizationStateError("invalid_localization_time")
        return float(value)

    def _touch(self):
        self._revision += 1

    def _mark_active_task_unknown(self, reason):
        if self._active_task is None:
            return
        self._last_task = {
            **self._active_task,
            "state": "UNKNOWN",
            "result": reason,
        }
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
            elif state not in {"enabled_stopped"}:
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
                self._last_observation_error = str(result.get("error", "vision_result_not_accepted")) if isinstance(result, dict) else "vision_result_invalid"
                self._touch()
                return
            if result.get("camera_calibration_ready") is not True or result.get("board_layout_ready") is not True:
                self._last_observation_error = "vision_calibration_unverified"
                self._touch()
                return
            raw_ids = result.get("used_ids")
            if (not isinstance(raw_ids, list) or any(
                    isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in raw_ids)):
                self._last_observation_error = "vision_used_ids_invalid"
                self._touch()
                return
            used_ids = sorted(set(raw_ids))
            if len(used_ids) < self.min_visible_tags:
                self._last_observation_error = "insufficient_visible_tags"
                self._touch()
                return
            try:
                transform = rigid_transform(result.get("T_camera_from_board"), "vision_transform_invalid")
            except GeometryError as error:
                self._last_observation_error = str(error)
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
            self._samples.append({
                "received_at": now,
                "transform": transform,
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
            try:
                mean, translation_spread, rotation_spread = average_transforms(
                    [item["transform"] for item in self._samples]
                )
            except GeometryError as error:
                self._reason = "vision_pose_unstable"
                self._last_observation_error = str(error)
                self._touch()
                return
            if translation_spread > self.max_translation_spread_mm or rotation_spread > self.max_rotation_spread_deg:
                self._reason = "vision_pose_unstable"
                self._touch()
                return
            T_base_from_board = compose(self.geometry.T_base_from_camera, mean)
            self._generation += 1
            all_ids = sorted({tag_id for item in self._samples for tag_id in item["used_ids"]})
            self._locked_context = {
                "generation": self._generation,
                "geometry_id": self.geometry.geometry_id,
                "frames": {
                    "base": self.geometry.base_frame,
                    "camera": self.geometry.camera_frame,
                    "board": self._samples[-1]["source_key"][2],
                    "tool0": self.geometry.tool_frame,
                    "pen": self.geometry.pen_frame,
                },
                "T_camera_from_board": transform_list(mean),
                "T_base_from_board": transform_list(T_base_from_board),
                "T_board_from_base": transform_list(inverse(T_base_from_board)),
                "T_tool0_from_pen": transform_list(self.geometry.T_tool0_from_pen),
                "T_pen_from_tool0": transform_list(inverse(self.geometry.T_tool0_from_pen)),
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
                    "translation_spread_mm": round(translation_spread, 6),
                    "rotation_spread_deg": round(rotation_spread, 6),
                },
            }
            self._state, self._reason = "locked", "stable_transform_locked"
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
            self._active_task = {"task_id": task_id, "generation": self._generation, "state": "RUNNING", "result": "none"}
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
                "settling_remaining_ms": remaining,
                "sample_count": len(self._samples),
                "min_valid_samples": self.min_valid_samples,
                "last_observation_error": self._last_observation_error,
                "context": deepcopy(self._locked_context),
                "task": {"active": deepcopy(self._active_task), "last": deepcopy(self._last_task)},
            }
