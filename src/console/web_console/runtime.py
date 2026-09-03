"""Stateful, UI-independent runtime for the localhost robot console."""

import math
import json
import threading
import time
import uuid
from collections import deque
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from runtime_core import MOTION_ARM_COMMANDS, RECOVERY_ARM_COMMANDS, close_client, default_arm_factory, default_chassis_factory, dispatch_arm, dispatch_chassis
import arm_fault_mapping
from status_mapping import StatusMappingError, parse_arm_status, parse_chassis_status


class WebConsoleError(RuntimeError):
    """An operator request cannot be completed safely or correctly."""

    def __init__(self, code, http_status=409):
        super().__init__(code)
        self.code = code
        self.http_status = http_status


class WebConsoleRuntime:
    """Own hardware sessions and expose sanitized state to one local browser."""

    INPUT_TIMEOUT_S = 1.0

    def __init__(self, config, chassis_factory=None, arm_factory=None, start_workers=True, clock=None, event_log_path=None):
        self.config = config
        self._chassis_factory = chassis_factory or default_chassis_factory
        self._arm_factory = arm_factory or default_arm_factory
        self._clock = clock or time.monotonic
        self._lock = threading.RLock()
        self._chassis_io = threading.RLock()
        self._arm_io = threading.RLock()
        self._chassis = None
        self._arm = None
        self._revision = 0
        self._event_index = 0
        self._events = deque(maxlen=80)
        self._faults = {}
        self._event_log_path = Path(event_log_path) if event_log_path else None
        self._log_error = None
        self._held_velocity = None
        self._motion_epoch = uuid.uuid4().hex
        self._input_deadline = None
        self._stops_pending = 0
        self._last_chassis_health = None
        self._last_arm_health = None
        self._last_arm_sample_received = None
        self._stop_event = threading.Event()
        self._threads = []
        self._state = {
            "video": {
                "configured": bool(config.video.webrtc_url),
                "webrtc_url": config.video.webrtc_url,
                "rotation_degrees": 90,
            },
            "chassis": {
                "link": "offline",
                "authenticated": False,
                "motion_permitted": False,
                "motion_enabled": False,
                "reported_state": "disconnected",
                "last_error": "none",
                "velocity": {"vx_mm_s": 0, "vy_mm_s": 0, "omega_mrad_s": 0},
                "motion": {"epoch": self._motion_epoch, "mode": "idle", "reason": "startup",
                           "refresh_count": 0, "input_timeout_ms": int(self.INPUT_TIMEOUT_S * 1000)},
                "limits": {
                    "linear_mm_s": config.manual_chassis.linear_limit_mm_s,
                    "angular_mrad_s": config.manual_chassis.angular_limit_mrad_s,
                    "hold_ms": config.manual_chassis.velocity_hold_ms,
                },
            },
            "arm": {
                "fault_capabilities": None,
                "fault_diagnostics": {},
                "last_fault": None,
                "recovery_result": None,
                "gateway": "offline",
                "controller": "offline",
                "task": "idle",
                "motion_permitted": False,
                "control_mode": "unknown",
                "reported_state": "disconnected",
                "last_error": "none",
                "measurement": {
                    "valid": False,
                    "joint_deg": None,
                    "pose": None,
                    "pose_user": 0,
                    "pose_tool": 0,
                    "sample_id": None,
                    "sample_time_ms": None,
                    "error": "unavailable",
                },
            },
        }
        if start_workers:
            self._start_workers()

    def _start_workers(self):
        for target, name in ((self._chassis_health_loop, "console-chassis-health"),
                             (self._arm_health_loop, "console-arm-health"),
                             (self._motion_loop, "console-motion")):
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
            self._threads.append(thread)

    def _touch(self):
        self._revision += 1

    def _event(self, target, command, lifecycle, result, evidence=None):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        with self._lock:
            self._event_index += 1
            self._events.appendleft({
                "id": self._event_index,
                "time": timestamp,
                "target": target,
                "command": command,
                "lifecycle": lifecycle,
                "result": str(result)[:160],
            })
            if evidence is not None:
                self._events[0]["evidence"] = deepcopy(evidence)
            self._touch()
            self._append_log("%s EVENT target=%s command=%s lifecycle=%s result=%s" % (timestamp, target, command, lifecycle, str(result)[:160]))
            if evidence is not None:
                self._append_log("%s ARM_EVIDENCE %s" % (timestamp, json.dumps(evidence, ensure_ascii=True, sort_keys=True)))

    def _fault(self, code, source, summary):
        with self._lock:
            self._faults[code] = {
                "code": code,
                "source": source,
                "summary": summary,
                "acknowledged": False,
            }
            self._touch()
            self._append_log("%s FAULT source=%s code=%s summary=%s" % (datetime.now().strftime("%H:%M:%S.%f")[:-3], source, code, summary))

    def _append_log(self, line):
        if self._event_log_path is None:
            return
        try:
            self._event_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._event_log_path.open("a", encoding="utf-8") as handle:
                handle.write(line.replace("\r", " ").replace("\n", " ") + "\n")
            self._log_error = None
        except OSError as error:
            # An unavailable log disk must never prevent STOP or input clearing.
            self._log_error = error.__class__.__name__

    def _clear_fault(self, code):
        with self._lock:
            if code in self._faults:
                del self._faults[code]
                self._touch()

    def snapshot(self):
        with self._lock:
            state = deepcopy(self._state)
            now = self._clock()
            state["chassis"]["health_age_ms"] = None if self._last_chassis_health is None else max(0, int((now - self._last_chassis_health) * 1000))
            state["chassis"]["motion"]["input_remaining_ms"] = None if self._input_deadline is None else max(0, int((self._input_deadline - now) * 1000))
            state["arm"]["health_age_ms"] = None if self._last_arm_health is None else max(0, int((now - self._last_arm_health) * 1000))
            state["arm"]["measurement"]["age_ms"] = None if self._last_arm_sample_received is None else max(0, int((now - self._last_arm_sample_received) * 1000))
            for diagnostic in state["arm"]["fault_diagnostics"].values():
                received = diagnostic.pop("received_monotonic_ms", None)
                diagnostic["age_ms"] = None if received is None else max(0, int(now * 1000 - received))
                diagnostic["fresh"] = bool(diagnostic.get("fresh") and received is not None and diagnostic["age_ms"] <= 5000)
            return {
                "revision": self._revision,
                "log_error": self._log_error,
                "video": state["video"],
                "chassis": state["chassis"],
                "arm": state["arm"],
                "faults": list(self._faults.values()),
                "events": list(self._events),
            }

    def _require_chassis(self):
        with self._lock:
            if self._chassis is None:
                raise WebConsoleError("chassis_offline")
            return self._chassis

    def _require_arm(self):
        with self._lock:
            if self._arm is None:
                raise WebConsoleError("arm_offline")
            return self._arm

    def connect_chassis(self):
        with self._chassis_io:
            return self._connect_chassis_locked()

    def _connect_chassis_locked(self):
        with self._lock:
            if self._chassis is not None:
                return self.snapshot()
        try:
            client = self._chassis_factory(self.config.chassis)
            with self._lock:
                self._chassis = client
                self._state["chassis"].update(link="online", authenticated=True, last_error="none")
                self._last_chassis_health = self._clock()
                self._touch()
            self.refresh_chassis_status(journal=False)
            self._clear_fault("chassis_connection_failed")
            self._event("ESP32", "connect", "DONE", "connected")
            return self.snapshot()
        except Exception as error:
            self._disconnect_chassis_state()
            self._fault("chassis_connection_failed", "esp32", self._error_code(error))
            self._event("ESP32", "connect", "FAULT", self._error_code(error))
            raise WebConsoleError("chassis_connection_failed", 503) from error

    def _disconnect_chassis_state(self):
        with self._lock:
            client, self._chassis = self._chassis, None
            self._cancel_motion("connection_closed")
            self._last_chassis_health = None
            self._state["chassis"].update(
                link="offline", authenticated=False, motion_permitted=False,
                motion_enabled=False, reported_state="disconnected",
                velocity={"vx_mm_s": 0, "vy_mm_s": 0, "omega_mrad_s": 0},
            )
            self._touch()
        close_client(client)

    def disconnect_chassis(self):
        self._cancel_motion("disconnect", stopping=True)
        try:
            with self._chassis_io:
                with self._lock:
                    client = self._chassis
                if client is not None:
                    for command in ("stop", "disable"):
                        try:
                            dispatch_chassis(client, command)
                        except Exception:
                            break
                self._disconnect_chassis_state()
        finally:
            self._finish_stop()
        self._event("ESP32", "disconnect", "DONE", "disconnected")
        return self.snapshot()

    @staticmethod
    def _error_code(error):
        return str(getattr(error, "code", None) or error.__class__.__name__).strip()[:80]

    def _chassis_request(self, command, payload=None, journal=True):
        with self._chassis_io:
            client = self._require_chassis()
            try:
                response = dispatch_chassis(client, command, payload)
                with self._lock:
                    self._last_chassis_health = self._clock()
                if journal:
                    self._event("ESP32", command, "DONE", "completed")
                return response
            except Exception as error:
                code = self._error_code(error)
                if getattr(error, "explicit_rejection", False):
                    if journal:
                        self._event("ESP32", command, "REJECTED", code)
                    raise WebConsoleError(code) from error
                self._disconnect_chassis_state()
                self._fault("chassis_transport_failed", "esp32", code)
                if journal:
                    self._event("ESP32", command, "FAULT", code)
                raise WebConsoleError("chassis_transport_failed", 503) from error

    def refresh_chassis_status(self, journal=True):
        # A late status response must not overwrite a subsequent STOP/Disable.
        with self._chassis_io:
            return self._refresh_chassis_status_locked(journal)

    def _refresh_chassis_status_locked(self, journal):
        response = self._chassis_request("status", journal=journal)
        try:
            status = parse_chassis_status(response)
        except StatusMappingError as error:
            self._fault("chassis_status_invalid", "esp32", str(error))
            raise WebConsoleError("chassis_status_invalid", 502) from error
        with self._lock:
            self._state["chassis"].update(
                link="online", authenticated=status.authenticated,
                motion_permitted=status.motion_permitted,
                motion_enabled=status.motion_enabled,
                reported_state=status.chassis_state,
                last_error=status.last_error,
            )
            self._last_chassis_health = self._clock()
            if not status.motion_enabled and self._held_velocity is not None:
                self._cancel_motion("device_disabled")
            self._touch()
        self._clear_fault("chassis_status_invalid")
        return self.snapshot()

    def enable_chassis(self):
        if not self.config.manual_chassis.enabled:
            raise WebConsoleError("manual_chassis_disabled")
        self._chassis_request("enable")
        return self.refresh_chassis_status(journal=False)

    def disable_chassis(self):
        self._cancel_motion("disable", stopping=True)
        try:
            with self._chassis_io:
                self._chassis_request("disable")
                return self.refresh_chassis_status(journal=False)
        finally:
            self._finish_stop()

    def _motion_log(self, event, reason):
        motion = self._state["chassis"]["motion"]
        self._append_log("%s MOTION event=%s epoch=%s mode=%s reason=%s refreshes=%d" % (
            datetime.now().strftime("%H:%M:%S.%f")[:-3], event, motion["epoch"],
            motion["mode"], reason, motion["refresh_count"]))

    def _cancel_motion(self, reason, stopping=False):
        """Invalidate work before waiting for I/O; never hold state lock over I/O."""
        with self._lock:
            self._motion_log("clear", reason)
            self._motion_epoch = uuid.uuid4().hex
            self._held_velocity = None
            self._input_deadline = None
            self._stops_pending += int(stopping)
            self._state["chassis"]["motion"].update(epoch=self._motion_epoch, mode="idle", reason=reason, refresh_count=0)
            self._state["chassis"]["velocity"] = {"vx_mm_s": 0, "vy_mm_s": 0, "omega_mrad_s": 0}
            self._touch()
            return self._motion_epoch

    def _finish_stop(self):
        with self._lock:
            self._stops_pending -= 1

    @staticmethod
    def _integer(value, name):
        if isinstance(value, bool) or not isinstance(value, int):
            raise WebConsoleError("invalid_" + name, 400)
        return value

    def _validate_velocity(self, payload):
        vx = self._integer(payload.get("vx_mm_s"), "vx")
        vy = self._integer(payload.get("vy_mm_s"), "vy")
        omega = self._integer(payload.get("omega_mrad_s"), "omega")
        linear_limit = self.config.manual_chassis.linear_limit_mm_s
        angular_limit = self.config.manual_chassis.angular_limit_mrad_s
        if math.hypot(vx, vy) > linear_limit or abs(omega) > angular_limit:
            raise WebConsoleError("velocity_out_of_range", 400)
        return {"vx_mm_s": vx, "vy_mm_s": vy, "omega_mrad_s": omega, "hold_ms": self.config.manual_chassis.velocity_hold_ms}

    def start_chassis_motion(self, payload):
        if not self.config.manual_chassis.enabled:
            raise WebConsoleError("manual_chassis_disabled")
        command = self._validate_velocity(payload)
        mode = payload.get("input_mode")
        if mode not in ("momentary", "hold") or not isinstance(payload.get("motion_epoch"), str):
            raise WebConsoleError("motion_metadata_required", 400)
        # Includes time spent waiting behind another device request.
        deadline = self._clock() + self.INPUT_TIMEOUT_S
        with self._chassis_io:
            with self._lock:
                chassis = self._state["chassis"]
                if payload["motion_epoch"] != self._motion_epoch or self._stops_pending or self._stop_event.is_set():
                    self._event("ESP32", "motion.start", "REJECTED", "stale_motion_epoch")
                    raise WebConsoleError("stale_motion_epoch")
                if self._clock() >= deadline:
                    raise WebConsoleError("motion_input_expired")
                if not (chassis["link"] == "online" and chassis["authenticated"] and chassis["motion_permitted"] and chassis["motion_enabled"]):
                    raise WebConsoleError("chassis_motion_not_enabled")
                epoch = self._cancel_motion("replaced")
                chassis["motion"].update(mode=mode, reason="starting")
                self._input_deadline = deadline
            try:
                self._chassis_request("velocity", command)
            except WebConsoleError:
                with self._lock:
                    if epoch == self._motion_epoch:
                        self._cancel_motion("start_failed")
                # A rejected replacement must not keep the old vector alive.
                if self._chassis is not None:
                    self.stop_chassis_motion(reason="start_failed")
                raise
            with self._lock:
                if epoch != self._motion_epoch:
                    raise WebConsoleError("motion_cancelled")
                expired = self._clock() >= deadline
                if not expired:
                    self._held_velocity = command
                    chassis["velocity"] = {key: command[key] for key in ("vx_mm_s", "vy_mm_s", "omega_mrad_s")}
                    chassis["motion"]["reason"] = "active"
                    self._motion_log("start", "operator_input")
                    self._touch()
            if expired:
                self.stop_chassis_motion(reason="browser_input_expired")
                raise WebConsoleError("motion_input_expired")
        return self.snapshot()

    def stop_chassis_motion(self, reason="operator_stop"):
        self._cancel_motion(reason, stopping=True)
        try:
            with self._chassis_io:
                if self._chassis is not None:
                    self._chassis_request("stop")
                    self.refresh_chassis_status(journal=False)
        finally:
            self._finish_stop()
        return self.snapshot()

    def keep_chassis_motion(self, payload):
        """Input presence only: cannot start motion, change vectors or revive expiry."""
        with self._chassis_io:
            with self._lock:
                if (payload.get("motion_epoch") != self._motion_epoch or self._held_velocity is None
                        or self._stops_pending or self._stop_event.is_set()):
                    raise WebConsoleError("stale_motion_epoch")
                expired = self._clock() >= self._input_deadline
                if not expired:
                    self._input_deadline = self._clock() + self.INPUT_TIMEOUT_S
            if expired:
                self.stop_chassis_motion(reason="browser_input_expired")
                raise WebConsoleError("motion_input_expired")
        return self.snapshot()

    def motion_once(self):
        # Never copy a command before obtaining I/O: STOP may have overtaken us.
        with self._chassis_io:
            with self._lock:
                command = self._held_velocity
                epoch = self._motion_epoch
                if command is None or self._stops_pending or self._stop_event.is_set():
                    return
                expired = self._clock() >= self._input_deadline
            try:
                if expired:
                    self.stop_chassis_motion(reason="browser_input_expired")
                    return
                self._chassis_request("velocity", command, journal=False)
                with self._lock:
                    if epoch == self._motion_epoch:
                        self._state["chassis"]["motion"]["refresh_count"] += 1
                        self._touch()
            except WebConsoleError as error:
                self._event("ESP32", "motion.refresh", "FAULT", error.code)
                self.stop_chassis_motion(reason="refresh_failed")

    def health_once(self):
        """Synchronous diagnostic tick; production workers use separate routes."""
        self.chassis_health_once()
        self.arm_health_once()

    def chassis_health_once(self):
        with self._lock:
            chassis_online = self._chassis is not None
        if chassis_online:
            try:
                self._chassis_request("ping", journal=False)
                self.refresh_chassis_status(journal=False)
            except WebConsoleError:
                pass
    def arm_health_once(self):
        # Do not queue a background poll behind an operator's arm command.
        if not self._arm_io.acquire(blocking=False):
            return
        try:
            with self._lock:
                arm_online = self._arm is not None
            if arm_online:
                try:
                    self.refresh_arm_status(journal=False)
                except WebConsoleError:
                    pass
        finally:
            self._arm_io.release()

    def _chassis_health_loop(self):
        interval = self.config.manual_chassis.health_interval_ms / 1000.0
        while not self._stop_event.wait(interval):
            self.chassis_health_once()

    def _arm_health_loop(self):
        # Wait after each completed read; never accumulate missed poll ticks.
        while not self._stop_event.wait(0.5):
            self.arm_health_once()

    def _motion_loop(self):
        interval = max(0.04, min(0.1, self.config.manual_chassis.velocity_hold_ms / 3000.0))
        while not self._stop_event.wait(interval):
            try:
                self.motion_once()
            except WebConsoleError:
                # Transport failures already close/clear only the chassis route.
                pass

    def connect_arm(self):
        with self._arm_io:
            return self._connect_arm_locked()

    def _connect_arm_locked(self):
        with self._lock:
            if self._arm is not None:
                return self.snapshot()
        try:
            client = self._arm_factory(self.config.arm)
            with self._lock:
                self._arm = client
                self._state["arm"].update(gateway="online", last_error="none")
                self._last_arm_health = self._clock()
                self._touch()
            self.refresh_arm_status(journal=False)
            self._clear_fault("arm_connection_failed")
            self._event("Arm", "connect", "DONE", "connected")
            return self.snapshot()
        except Exception as error:
            self._disconnect_arm_state()
            self._fault("arm_connection_failed", "maixcam", self._error_code(error))
            self._event("Arm", "connect", "FAULT", self._error_code(error))
            raise WebConsoleError("arm_connection_failed", 503) from error

    def _disconnect_arm_state(self):
        with self._lock:
            client, self._arm = self._arm, None
            self._last_arm_health = None
            self._state["arm"].update(
                gateway="offline", controller="offline", task="idle",
                motion_permitted=False, control_mode="unknown",
                reported_state="disconnected",
            )
            self._state["arm"]["measurement"].update(valid=False, error="disconnected")
            self._state["arm"]["fault_capabilities"] = None
            for diagnostic in self._state["arm"]["fault_diagnostics"].values():
                diagnostic["fresh"] = False
            self._touch()
        close_client(client)

    def disconnect_arm(self):
        with self._arm_io:
            self._disconnect_arm_state()
        self._event("Arm", "disconnect", "DONE", "disconnected")
        return self.snapshot()

    def _arm_request(self, command, payload=None, journal=True):
        with self._arm_io:
            client = self._require_arm()
            try:
                response = dispatch_arm(client, command, payload)
                with self._lock:
                    self._last_arm_health = self._clock()
                if journal:
                    self._event("Arm", command, "DONE", "completed")
                return response
            except Exception as error:
                code = self._error_code(error)
                outcome = getattr(error, "lifecycle", None)
                known_failure = getattr(error, "explicit_terminal", False) and outcome in {"REJECTED", "FAULT"}
                if known_failure or getattr(error, "explicit_rejection", False):
                    outcome = outcome or "REJECTED"
                    with self._lock:
                        self._last_arm_health = self._clock()
                        self._state["arm"]["last_error"] = code
                        self._touch()
                    evidence = None
                    downstream = getattr(error, "payload", {}).get("downstream_payload")
                    if downstream:
                        try:
                            evidence = arm_fault_mapping.fault(downstream)
                            evidence["received_at"] = datetime.now().astimezone().isoformat(timespec="milliseconds")
                            evidence["command"] = command
                            evidence["downstream_sequence"] = error.payload.get("downstream_sequence")
                        except (ValueError, KeyError):
                            evidence = {"error_code": "invalid_fault_evidence"}
                    self._record_arm_fault(code, repeat=not journal, evidence=evidence)
                    if journal:
                        self._event("Arm", command, outcome, code, evidence=evidence)
                    raise WebConsoleError(code) from error
                self._disconnect_arm_state()
                self._fault("arm_transport_failed", "maixcam", code)
                if journal:
                    outcome = outcome or ("UNKNOWN" if command in MOTION_ARM_COMMANDS | RECOVERY_ARM_COMMANDS else "FAULT")
                    self._event("Arm", command, outcome, code)
                raise WebConsoleError(code, 503) from error

    def _record_arm_fault(self, code, repeat=False, evidence=None):
        """Retain errors without re-arming acknowledgement on every status poll."""
        key = "arm_" + code
        with self._lock:
            if not repeat or key not in self._faults:
                self._fault(key, "arm", code)
            if evidence is not None:
                self._faults[key]["evidence"] = deepcopy(evidence)
                self._state["arm"]["last_fault"] = deepcopy(evidence)

    def arm_diagnostics(self):
        """Explicit non-motion queries; never probe an unsupported clear path."""
        with self._arm_io:
            with self._lock:
                self._state["arm"]["fault_capabilities"] = None
                for diagnostic in self._state["arm"]["fault_diagnostics"].values():
                    diagnostic["fresh"] = False
            response = self._arm_request("capabilities", journal=False)
            try:
                caps = arm_fault_mapping.capabilities(arm_fault_mapping.raw_payload(response))
            except (ValueError, KeyError, TypeError) as error:
                raise WebConsoleError("invalid_fault_capabilities", 502) from error
            with self._lock:
                self._state["arm"]["fault_capabilities"] = caps
            for scope in ("service", "controller"):
                if scope == "controller" and not caps["controller_query"]:
                    with self._lock:
                        self._state["arm"]["fault_diagnostics"][scope] = {"supported": False, "fresh": False}
                    continue
                response = self._arm_request("faults", {"scope": scope}, journal=False)
                try:
                    parse = arm_fault_mapping.fault if scope == "service" else arm_fault_mapping.controller_state
                    detail = parse(arm_fault_mapping.raw_payload(response))
                except (ValueError, KeyError, TypeError) as error:
                    raise WebConsoleError("invalid_fault_diagnostics", 502) from error
                detail.update(supported=True, fresh=True, received_monotonic_ms=int(self._clock() * 1000), received_at=datetime.now().astimezone().isoformat(timespec="milliseconds"))
                with self._lock:
                    self._state["arm"]["fault_diagnostics"][scope] = detail
                    self._touch()
                if scope == "service" and detail["error_code"] != "none":
                    self._record_arm_fault(detail["error_code"], repeat=True, evidence=detail)
                self._event("Arm", "faults_" + scope, "DONE", "snapshot", evidence=detail)
            return self.snapshot()

    def arm_recovery(self, action, confirm=False):
        if action not in RECOVERY_ARM_COMMANDS:
            raise WebConsoleError("unsupported_recovery_action", 400)
        if confirm is not True:
            raise WebConsoleError("recovery_confirmation_required", 400)
        with self._lock:
            if self._state["arm"]["task"] == "running" or self._state["arm"]["recovery_result"] == "pending":
                raise WebConsoleError("arm_request_in_flight")
            self._state["arm"]["recovery_result"] = "pending"
            self._touch()
        with self._arm_io:
            try:
                # Re-read capabilities, not a stale browser assertion.
                response = self._arm_request("capabilities", journal=False)
                caps = arm_fault_mapping.capabilities(arm_fault_mapping.raw_payload(response))
                capability = "controller_clear" if action == "clear_errors" else "service_recover"
                with self._lock:
                    self._state["arm"]["fault_capabilities"] = caps
                if not caps[capability]:
                    raise WebConsoleError(capability + "_unsupported")
                response = self._arm_request(action, {"confirm": True}, journal=False)
                payload = arm_fault_mapping.raw_payload(response)
                if action == "clear_errors":
                    result = arm_fault_mapping.controller_state(payload, cleared=True)
                    if result["controller_state"] != "clear" or not result["stationary"] or not result["queue_empty"] or result["emergency_stop"]:
                        raise WebConsoleError("controller_clear_unconfirmed")
                elif payload != "recovery=service_ready;motion_resumed=0":
                    raise WebConsoleError("service_recovery_unconfirmed")
                else:
                    result = {"recovery": "service_ready", "motion_resumed": False}
                with self._lock:
                    self._state["arm"]["recovery_result"] = "confirmed"
                self._event("Arm", action, "DONE", "confirmed_no_resume", evidence=result)
            except Exception as error:
                with self._lock:
                    self._state["arm"]["recovery_result"] = "unsupported" if self._error_code(error).endswith("_unsupported") else "unconfirmed"
                    self._touch()
                cause = error.__cause__
                outcome = getattr(cause, "lifecycle", None) or ("UNKNOWN" if isinstance(error, WebConsoleError) and error.http_status == 503 else "FAULT")
                self._event("Arm", action, outcome, self._error_code(error), evidence=getattr(cause, "payload", None))
                if isinstance(error, WebConsoleError):
                    raise
                raise WebConsoleError("invalid_recovery_response", 502) from error
            return self.refresh_arm_status(journal=False)

    def refresh_arm_status(self, journal=True):
        responses = self._arm_request("status", journal=journal)
        try:
            status = parse_arm_status(responses)
        except StatusMappingError as error:
            self._fault("arm_status_invalid", "maixcam", str(error))
            raise WebConsoleError("arm_status_invalid", 502) from error
        with self._lock:
            self._state["arm"].update(
                gateway="online", controller="online" if status.service_state != "fault" else "fault",
                task="running" if status.service_state == "running" else "idle",
                motion_permitted=status.motion_permitted,
                control_mode=status.control_mode,
                reported_state=status.service_state,
                last_error=status.last_error,
            )
            measurement = self._state["arm"]["measurement"]
            if status.feedback_valid:
                measurement.update(
                    valid=True,
                    joint_deg=list(status.joint_deg),
                    pose=list(status.pose),
                    pose_user=status.pose_user,
                    pose_tool=status.pose_tool,
                    sample_id=status.sample_id,
                    sample_time_ms=status.sample_time_ms,
                    error="none",
                )
                self._last_arm_sample_received = self._clock()
            else:
                measurement.update(valid=False, error=status.feedback_error)
            self._last_arm_health = self._clock()
            self._touch()
        self._clear_fault("arm_status_invalid")
        if status.last_error != "none":
            self._record_arm_fault(status.last_error, repeat=True)
        elif status.service_state == "fault":
            self._record_arm_fault("controller_fault", repeat=True)
        return self.snapshot()

    @staticmethod
    def _finite_list(value, length, code):
        if not isinstance(value, list) or len(value) != length:
            raise WebConsoleError(code, 400)
        result = []
        for item in value:
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
                raise WebConsoleError(code, 400)
            result.append(float(item))
        return result

    @classmethod
    def _arm_integer(cls, value, low, high, code):
        # JSON 20 and 20.0 both represent an integral value; never round 20.5.
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not low <= value <= high or int(value) != value):
            raise WebConsoleError(code, 400)
        return int(value)

    @classmethod
    def _arm_payload(cls, command, payload):
        payload = payload if isinstance(payload, dict) else {}
        if command in {"move_joint", "jog_joint"}:
            key = "joint_deg" if command == "move_joint" else "joint_delta_deg"
            clean = {key: cls._finite_list(payload.get(key), 6, "invalid_arm_vector")}
        elif command == "move_linear":
            clean = {"pose": cls._finite_list(payload.get("pose"), 6, "invalid_arm_pose")}
        elif command == "jog_xyz":
            clean = {"translation_mm": cls._finite_list(payload.get("translation_mm"), 3, "invalid_arm_vector")}
        elif command == "gripper":
            return {"width_mm": cls._arm_integer(payload.get("width_mm"), 0, 70, "invalid_gripper_width")}
        else:
            raise WebConsoleError("unsupported_arm_command", 400)
        for field in ("accel_pct", "speed_pct"):
            clean[field] = cls._arm_integer(payload.get(field, 5), 1, 100, "invalid_" + field)
        if command in {"move_linear", "jog_xyz"}:
            for field in ("user", "tool"):
                value = payload.get(field, 0)
                if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 9:
                    raise WebConsoleError("invalid_" + field, 400)
                clean[field] = value
        return clean

    def arm_command(self, command, payload):
        clean = self._arm_payload(command, payload)
        with self._lock:
            arm = self._state["arm"]
            if arm["recovery_result"] == "pending":
                raise WebConsoleError("arm_recovery_in_progress")
            if not (arm["gateway"] == "online" and arm["controller"] == "online" and arm["motion_permitted"]):
                raise WebConsoleError("arm_motion_not_enabled")
            arm["task"] = "running"
            self._touch()
        try:
            self._arm_request(command, clean)
        finally:
            with self._lock:
                self._state["arm"]["task"] = "idle"
                self._touch()
        return self.snapshot()

    def acknowledge_fault(self, code):
        with self._lock:
            fault = self._faults.get(code)
            if fault is None:
                raise WebConsoleError("fault_not_found", 404)
            fault["acknowledged"] = True
            self._touch()
            self._append_log("%s ACK source=%s code=%s" % (datetime.now().strftime("%H:%M:%S.%f")[:-3], fault["source"], code))
        return self.snapshot()

    def close(self):
        self._stop_event.set()
        try:
            self.disconnect_chassis()
        except Exception:
            pass
        self._disconnect_arm_state()
        for thread in self._threads:
            thread.join(timeout=1.0)
