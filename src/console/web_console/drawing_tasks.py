"""Backend-owned drawing task lifecycle with immutable per-run mode selection."""

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

from drawing import (
    DrawingError,
    build_drawing_plan,
    load_drawing_site_config,
    load_drawing_job,
    validate_job_canvas,
)


MODES = ("baseline", "localized_baseline", "advanced")


class DrawingTaskError(RuntimeError):
    """A drawing task request is invalid or cannot be admitted safely."""

    def __init__(self, code, http_status=409):
        super().__init__(code)
        self.code = code
        self.http_status = http_status


@dataclass(frozen=True)
class PreparedDrawing:
    task_id: str
    job_id: str
    mode: str
    site_config: object
    job: object
    drawing_config: object
    control_config: object
    board: object
    readiness: dict


def _contained_path(root, raw, label):
    if not isinstance(raw, str) or not raw.strip():
        raise DrawingTaskError("invalid_" + label, 400)
    root = root.resolve()
    path = (root / raw).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise DrawingTaskError(label + "_outside_repository", 400) from error
    return path


def load_drawing_web_policy(path, repository_root):
    """Load the Web-only job allowlist and log location."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DrawingTaskError("cannot_read_drawing_web_config") from error
    if not isinstance(raw, dict) or set(raw) != {
        "version", "jobs", "execution_log_directory",
    }:
        raise DrawingTaskError("invalid_drawing_web_config")
    if isinstance(raw["version"], bool) or raw["version"] != 1:
        raise DrawingTaskError("unsupported_drawing_web_config_version")
    jobs = raw["jobs"]
    if not isinstance(jobs, dict) or not jobs:
        raise DrawingTaskError("drawing_web_jobs_required")
    clean_jobs = {}
    for job_id, relative_path in jobs.items():
        if not isinstance(job_id, str) or not job_id.strip():
            raise DrawingTaskError("invalid_drawing_job_id")
        path = _contained_path(repository_root, relative_path, "drawing_job_path")
        if path.suffix.lower() != ".json":
            raise DrawingTaskError("web_drawing_requires_json_job")
        clean_jobs[job_id] = path
    log_directory = _contained_path(
        repository_root, raw["execution_log_directory"], "drawing_log_directory"
    )
    return {
        "jobs": clean_jobs,
        "execution_log_directory": log_directory,
    }


class DrawingTaskManager:
    """Prepare, start and cancel one drawing task without hot mode switching."""

    def __init__(
        self,
        repository_root,
        site_config_path,
        policy_path,
        execute_callback,
        acquire_callback,
        release_callback,
        cancel_callback,
        prerequisites_callback,
        changed_callback=None,
        thread_factory=None,
    ):
        self.root = Path(repository_root).resolve()
        self.site_config_path = Path(site_config_path)
        self.policy_path = Path(policy_path)
        self.execute_callback = execute_callback
        self.acquire_callback = acquire_callback
        self.release_callback = release_callback
        self.cancel_callback = cancel_callback
        self.prerequisites_callback = prerequisites_callback
        self.changed_callback = changed_callback or (lambda: None)
        self.thread_factory = thread_factory or threading.Thread
        self._lock = threading.RLock()
        self._lifecycle_lock = threading.RLock()
        self._cancel = threading.Event()
        self._thread = None
        self._prepared = None
        self._policy = load_drawing_web_policy(self.policy_path, self.root)
        self._state = {
            "configured": self._policy is not None,
            "state": "idle" if self._policy is not None else "unconfigured",
            "task_id": None,
            "job_id": None,
            "mode": None,
            "job_sha256": None,
            "drawing_config_sha256": None,
            "standard_start": None,
            "groups": 0,
            "strokes": 0,
            "points": 0,
            "first_window_complete": None,
            "first_checkpoint": None,
            "readiness": {},
            "phase": "idle" if self._policy is not None else "configuration_required",
            "last_event": None,
            "result": None,
            "error": "none",
            "cancel_pending": False,
            "log_path": None,
        }

    def _changed(self):
        self.changed_callback()

    def snapshot(self):
        with self._lock:
            result = dict(self._state)
            result["readiness"] = dict(self._state["readiness"])
            result["available_jobs"] = [] if self._policy is None else sorted(self._policy["jobs"])
            return result

    def _require_configured(self):
        if self._policy is None:
            raise DrawingTaskError("drawing_web_not_configured")

    def _readiness(self, mode, drawing_config, control_config):
        runtime = self.prerequisites_callback(mode, control_config)
        return {
            "site_config": bool(drawing_config.production_ready),
            "runtime": bool(runtime),
        }

    def prepare(self, request):
        self._require_configured()
        job_id = request.get("job_id")
        if job_id not in self._policy["jobs"]:
            raise DrawingTaskError("drawing_job_not_allowed", 400)
        with self._lock:
            if self._state["state"] in ("running", "stopping"):
                raise DrawingTaskError("drawing_mode_locked_while_active")
        try:
            site_config = load_drawing_site_config(self.site_config_path)
            drawing_config = site_config.drawing
            loaded_control = site_config.control
            mode = loaded_control.selected_mode
            control_config = replace(
                loaded_control,
                selected_mode=mode,
            )
            if mode == "localized_baseline" and control_config.localized_baseline is None:
                raise DrawingError("localized_baseline_unavailable_in_config")
            job = load_drawing_job(
                self._policy["jobs"][job_id],
                flat_group_name=drawing_config.flat_group_name,
            )
            board = validate_job_canvas(job, drawing_config)
            initial_offset = (
                control_config.baseline.initial_json_axis_offset_mm
                if mode == "baseline" else 0.0
            )
            first_plan = build_drawing_plan(job, drawing_config, initial_offset)
        except DrawingError as error:
            raise DrawingTaskError(getattr(error, "code", str(error)), 400) from error
        readiness = self._readiness(mode, drawing_config, control_config)
        prepared = PreparedDrawing(
            uuid.uuid4().hex,
            job_id,
            mode,
            site_config,
            job,
            drawing_config,
            control_config,
            board,
            readiness,
        )
        with self._lock:
            self._prepared = prepared
            self._cancel.clear()
            self._state.update(
                state="prepared",
                task_id=prepared.task_id,
                job_id=job_id,
                mode=mode,
                job_sha256=job.canonical_sha256,
                drawing_config_sha256=drawing_config.canonical_sha256,
                standard_start={
                    "physical_start_mm": site_config.rail.physical_start_mm,
                    "json_origin_rail_position_mm": site_config.rail.json_origin_rail_position_mm,
                    "start_tolerance_mm": site_config.rail.start_tolerance_mm,
                    "measured": mode != "baseline",
                },
                groups=len(job.groups),
                strokes=job.stroke_count,
                points=job.point_count,
                first_window_complete=first_plan.complete,
                first_checkpoint=(
                    None if first_plan.next_checkpoint is None
                    else first_plan.next_checkpoint.to_dict()
                ),
                readiness=readiness,
                phase="prepared",
                last_event=None,
                result=None,
                error="none",
                cancel_pending=False,
                log_path=None,
            )
        self._changed()
        return self.snapshot()

    def start(self, request):
        if request.get("attended") is not True:
            raise DrawingTaskError("drawing_attended_confirmation_required", 400)
        with self._lock:
            prepared = self._prepared
            if self._state["state"] != "prepared" or prepared is None:
                raise DrawingTaskError("drawing_task_not_prepared")
            if request.get("task_id") != prepared.task_id:
                raise DrawingTaskError("drawing_task_id_mismatch", 400)
            if not all(prepared.readiness.values()):
                raise DrawingTaskError("drawing_mode_not_production_ready")
        self.acquire_callback(prepared)
        try:
            with self._lock:
                if self._state["state"] != "prepared" or self._prepared is not prepared:
                    raise DrawingTaskError("drawing_task_changed_before_start")
                self._cancel.clear()
                timestamp = time.strftime("%Y%m%d-%H%M%S")
                log_path = self._policy["execution_log_directory"] / (
                    "%s-%s-%s.jsonl" % (timestamp, prepared.mode, prepared.task_id[:8])
                )
                self._state.update(
                    state="running", phase="starting", cancel_pending=False,
                    result=None, error="none",
                    log_path=str(log_path.relative_to(self.root)),
                )
                self._thread = self.thread_factory(
                    target=self._run,
                    args=(prepared, True, log_path),
                    name="web-drawing-task",
                    daemon=True,
                )
                self._thread.start()
        except Exception:
            with self._lock:
                if self._prepared is prepared:
                    self._state.update(
                        state="prepared", phase="prepared", log_path=None,
                    )
            self.release_callback()
            self._changed()
            raise
        self._changed()
        return self.snapshot()

    def _emit(self, log_stream, event):
        record = {"time_ms": int(time.time() * 1000), **dict(event)}
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        log_stream.write(line + "\n")
        name = str(record.get("event") or record.get("state") or "")
        if (
            name.startswith("drawing_task_")
            or name in {"execution_stopped", "execution_failed"}
            or name.endswith("_window_done")
            or name.endswith("_relocation_done")
        ):
            log_stream.flush()
            os.fsync(log_stream.fileno())
        with self._lock:
            self._state["phase"] = str(record.get("event") or record.get("state") or "running")
            self._state["last_event"] = record
        self._changed()

    def _run(self, prepared, attended, log_path):
        terminal = "failed"
        result = None
        error_code = "drawing_execution_failed"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("x", encoding="utf-8") as stream:
                self._emit(stream, {
                    "event": "drawing_task_started",
                    "task_id": prepared.task_id,
                    "job_id": prepared.job_id,
                    "mode": prepared.mode,
                    "job_sha256": prepared.job.canonical_sha256,
                })
                result = self.execute_callback(
                    prepared, attended, self._cancel,
                    lambda event: self._emit(stream, event),
                )
                terminal = "cancelled" if self._cancel.is_set() else "completed"
                self._emit(stream, {
                    "event": "drawing_task_" + terminal,
                    "task_id": prepared.task_id,
                    "result": result,
                })
        except Exception as error:
            error_code = str(getattr(error, "code", None) or error).strip()[:120]
            if self._cancel.is_set() or error_code == "drawing_cancelled":
                terminal = "cancelled"
                error_code = "none"
            try:
                with log_path.open("a", encoding="utf-8") as stream:
                    self._emit(stream, {
                        "event": "drawing_task_" + terminal,
                        "task_id": prepared.task_id,
                        "error": error_code,
                    })
            except OSError:
                pass
        finally:
            try:
                self.release_callback()
            finally:
                with self._lock:
                    self._state.update(
                        state=terminal,
                        phase=terminal,
                        result=result,
                        error=error_code if terminal == "failed" else "none",
                        cancel_pending=False,
                    )
                self._changed()

    def cancel(self, request):
        with self._lock:
            task_id = self._state["task_id"]
            if request.get("task_id") != task_id:
                raise DrawingTaskError("drawing_task_id_mismatch", 400)
            state = self._state["state"]
            if state == "prepared":
                self._cancel.set()
                self._state.update(state="cancelled", phase="cancelled", cancel_pending=False)
                self._changed()
                return self.snapshot()
            if state not in ("running", "stopping"):
                return self.snapshot()
            self._cancel.set()
            self._state.update(state="stopping", phase="cancellation_requested", cancel_pending=True)
        self._changed()
        self.cancel_callback()
        return self.snapshot()

    def handle(self, request):
        if not isinstance(request, dict):
            raise DrawingTaskError("drawing_request_must_be_object", 400)
        with self._lifecycle_lock:
            action = request.get("action")
            if action == "prepare":
                return self.prepare(request)
            if action == "start":
                return self.start(request)
            if action == "cancel":
                return self.cancel(request)
            raise DrawingTaskError("invalid_drawing_action", 400)

    def raise_if_cancelled(self):
        if self._cancel.is_set():
            raise DrawingTaskError("drawing_cancelled")

    def sleep(self, seconds):
        if self._cancel.wait(max(0.0, float(seconds))):
            raise DrawingTaskError("drawing_cancelled")

    def wait(self, timeout=None):
        with self._lock:
            thread = self._thread
        if thread is not None:
            thread.join(timeout)
        return self.snapshot()

    def close(self):
        with self._lock:
            active = self._state["state"] in ("running", "stopping")
            task_id = self._state["task_id"]
        if active:
            self.handle({"action": "cancel", "task_id": task_id})
            self.wait(2.0)
