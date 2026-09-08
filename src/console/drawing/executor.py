"""Guarded, non-retrying execution of one complete arm-only drawing plan."""

import time
from dataclasses import dataclass

from status_mapping import parse_arm_status

from .models import DrawingError


class DrawingExecutionError(RuntimeError):
    """Execution stopped and no later plan command was submitted."""

    def __init__(self, code, completed_commands=0):
        RuntimeError.__init__(self, code)
        self.code = code
        self.completed_commands = completed_commands


@dataclass(frozen=True)
class DrawingExecutionAdmission:
    operator_present: bool
    emergency_stop_ready: bool
    area_clear: bool
    arm_profile_reviewed: bool

    def require(self):
        if not all(
            (
                self.operator_present,
                self.emergency_stop_ready,
                self.area_clear,
                self.arm_profile_reviewed,
            )
        ):
            raise DrawingExecutionError("execution_admission_required")


def flatten_plan_steps(plan):
    """Return immutable atomic steps; reject relocation and unknown wrappers."""
    if not plan.complete or plan.next_checkpoint is not None:
        raise DrawingError("complete_drawing_plan_required")
    return _flatten_steps(plan.steps)


def flatten_plan_window(plan):
    """Return the executable prefix before one verified reposition barrier."""
    if plan.complete:
        return flatten_plan_steps(plan)
    if plan.next_checkpoint is None or not plan.steps:
        raise DrawingError("drawing_plan_has_no_reposition_barrier")
    barrier = plan.steps[-1]
    if barrier.kind != "reposition.required":
        raise DrawingError("drawing_plan_has_no_reposition_barrier")
    prefix = plan.steps[:-1]
    if not prefix:
        raise DrawingError("drawing_window_does_not_end_arm_safe")
    final = prefix[-1]
    if (
        final.kind != "arm.home"
        or final.payload.get("purpose") != "reposition_safe_pose"
    ):
        raise DrawingError("drawing_window_does_not_end_arm_safe")
    return _flatten_steps(prefix)


def _flatten_steps(steps):
    flattened = []
    for step in steps:
        if step.kind in ("arm.home", "arm.relative", "sleep"):
            kind = "arm.move_joint" if step.kind == "arm.home" else step.kind
            flattened.append((step.label, kind, dict(step.payload)))
            continue
        if step.kind not in ("pen.select", "pen.return"):
            raise DrawingError("unsupported_plan_step: %s" % step.kind)
        nested = step.payload.get("steps")
        if not isinstance(nested, list) or not nested:
            raise DrawingError("invalid_pen_plan")
        for index, item in enumerate(nested, 1):
            if not isinstance(item, dict) or item.get("kind") not in (
                "arm.move_joint",
                "arm.relative",
                "arm.gripper",
            ):
                raise DrawingError("invalid_pen_plan")
            payload = dict(item)
            kind = payload.pop("kind")
            flattened.append(("%s step %d" % (step.label, index), kind, payload))
    return tuple(flattened)


def _require_done(result, code):
    if not isinstance(result, (list, tuple)) or not result:
        raise DrawingExecutionError(code)
    terminal = result[-1]
    if not isinstance(terminal, dict) or terminal.get("lifecycle") != "DONE":
        payload = terminal.get("payload", {}) if isinstance(terminal, dict) else {}
        raise DrawingExecutionError(payload.get("error_code", code))


def require_ready_arm(client, config):
    _require_done(client.ping(), "arm_ping_failed")
    responses = client.status()
    status = parse_arm_status(responses)
    if (
        status.service_state != "ready"
        or not status.motion_permitted
        or status.control_mode != "yolo"
        or status.active_sequence != 0
        or status.last_error != "none"
        or not status.feedback_valid
        or status.pose_user != config.geometry.user
        or status.pose_tool != config.geometry.tool
    ):
        raise DrawingExecutionError("arm_preflight_rejected")
    return status


def _execute_atomic(client, kind, payload, sleep_func):
    if kind == "sleep":
        sleep_func(payload["seconds"])
        return None
    if kind == "arm.move_joint":
        return client.move_joint(
            payload["joint_deg"],
            accel_pct=payload["accel_pct"],
            speed_pct=payload["speed_pct"],
        )
    if kind == "arm.relative":
        return client.jog_xyz(
            payload["translation_mm"],
            user=payload["user"],
            tool=payload["tool"],
            accel_pct=payload["accel_pct"],
            speed_pct=payload["speed_pct"],
            blend_pct=payload.get("blend_pct", 0),
        )
    if kind == "arm.gripper":
        return client.gripper(payload["width_mm"])
    raise DrawingExecutionError("unsupported_atomic_step")


def _execute_steps(
    client, steps, config, admission, emit, sleep_func, event_prefix
):
    admission.require()
    if not config.production_ready:
        raise DrawingExecutionError("drawing_not_production_ready")
    status = require_ready_arm(client, config)
    emit(
        {
            "event": event_prefix + "_ready",
            "commands_total": sum(kind != "sleep" for _, kind, _ in steps),
            "steps_total": len(steps),
            "feedback_sample_id": status.sample_id,
        }
    )
    completed_commands = 0
    for index, (label, kind, payload) in enumerate(steps, 1):
        emit({"event": "step_start", "index": index, "kind": kind, "label": label})
        try:
            result = _execute_atomic(client, kind, payload, sleep_func)
            if kind != "sleep":
                _require_done(result, "arm_command_failed")
                completed_commands += 1
        except Exception as error:
            emit(
                {
                    "event": "execution_stopped",
                    "index": index,
                    "kind": kind,
                    "label": label,
                    "completed_commands": completed_commands,
                    "error_code": getattr(error, "code", type(error).__name__),
                }
            )
            if isinstance(error, DrawingExecutionError):
                error.completed_commands = completed_commands
                raise
            raise DrawingExecutionError(
                getattr(error, "code", "arm_command_exception"),
                completed_commands,
            ) from error
        emit({"event": "step_done", "index": index, "kind": kind})
    emit({"event": event_prefix + "_done", "completed_commands": completed_commands})
    return {"completed_commands": completed_commands, "steps_total": len(steps)}


def execute_drawing_plan(
    client,
    plan,
    config,
    admission,
    event_sink=None,
    sleep_func=time.sleep,
):
    """Execute one complete plan. Any failure stops without retry or resume."""
    steps = flatten_plan_steps(plan)
    return _execute_steps(
        client, steps, config, admission, event_sink or (lambda _event: None),
        sleep_func, "execution",
    )


def execute_drawing_window(
    client,
    plan,
    config,
    admission,
    event_sink=None,
    sleep_func=time.sleep,
):
    """Execute a complete plan or only the arm-safe prefix before its barrier."""
    steps = flatten_plan_window(plan)
    result = _execute_steps(
        client, steps, config, admission, event_sink or (lambda _event: None),
        sleep_func, "window",
    )
    return {
        **result,
        "complete": plan.complete,
        "checkpoint": (
            None if plan.next_checkpoint is None else plan.next_checkpoint.to_dict()
        ),
    }
