"""Stateful, UI-independent runtime for the localhost robot console."""

import math
import threading
import time
from collections import deque
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from runtime_core import MOTION_ARM_COMMANDS, close_client, default_arm_factory, default_chassis_factory, dispatch_arm, dispatch_chassis
from status_mapping import StatusMappingError, parse_arm_status, parse_chassis_status


class WebConsoleError(RuntimeError):
    """An operator request cannot be completed safely or correctly."""

    def __init__(self, code, http_status=409):
        super().__init__(code)
        self.code = code
        self.http_status = http_status


class WebConsoleRuntime:
    """Own hardware sessions and expose sanitized state to one local browser."""

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
        self._held_velocity = None
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
                "limits": {
                    "linear_mm_s": config.manual_chassis.linear_limit_mm_s,
                    "angular_mrad_s": config.manual_chassis.angular_limit_mrad_s,
                    "hold_ms": config.manual_chassis.velocity_hold_ms,
                },
            },
            "arm": {
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

    def _event(self, target, command, lifecycle, result):
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
            self._touch()
            self._append_log("%s EVENT target=%s command=%s lifecycle=%s result=%s" % (timestamp, target, command, lifecycle, str(result)[:160]))

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
        self._event_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._event_log_path.open("a", encoding="utf-8") as handle:
            handle.write(line.replace("\r", " ").replace("\n", " ") + "\n")

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
            state["arm"]["health_age_ms"] = None if self._last_arm_health is None else max(0, int((now - self._last_arm_health) * 1000))
            state["arm"]["measurement"]["age_ms"] = None if self._last_arm_sample_received is None else max(0, int((now - self._last_arm_sample_received) * 1000))
            return {
                "revision": self._revision,
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
            self._held_velocity = None
            self._last_chassis_health = None
            self._state["chassis"].update(
                link="offline", authenticated=False, motion_permitted=False,
                motion_enabled=False, reported_state="disconnected",
                velocity={"vx_mm_s": 0, "vy_mm_s": 0, "omega_mrad_s": 0},
            )
            self._touch()
        close_client(client)

    def disconnect_chassis(self):
        with self._chassis_io:
            with self._lock:
                client = self._chassis
                self._held_velocity = None
            if client is not None:
                for command in ("stop", "disable"):
                    try:
                        dispatch_chassis(client, command)
                    except Exception:
                        break
            self._disconnect_chassis_state()
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
            self._touch()
        self._clear_fault("chassis_status_invalid")
        return self.snapshot()

    def enable_chassis(self):
        if not self.config.manual_chassis.enabled:
            raise WebConsoleError("manual_chassis_disabled")
        self._chassis_request("enable")
        return self.refresh_chassis_status(journal=False)

    def disable_chassis(self):
        with self._lock:
            self._held_velocity = None
        self._chassis_request("disable")
        return self.refresh_chassis_status(journal=False)

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
        with self._lock:
            chassis = self._state["chassis"]
            if not (chassis["link"] == "online" and chassis["authenticated"] and chassis["motion_permitted"] and chassis["motion_enabled"]):
                raise WebConsoleError("chassis_motion_not_enabled")
        self._chassis_request("velocity", command)
        with self._lock:
            self._held_velocity = command
            self._state["chassis"]["velocity"] = {key: command[key] for key in ("vx_mm_s", "vy_mm_s", "omega_mrad_s")}
            self._touch()
        return self.snapshot()

    def stop_chassis_motion(self):
        with self._lock:
            self._held_velocity = None
            self._state["chassis"]["velocity"] = {"vx_mm_s": 0, "vy_mm_s": 0, "omega_mrad_s": 0}
            online = self._chassis is not None
            self._touch()
        if online:
            self._chassis_request("stop")
            self.refresh_chassis_status(journal=False)
        return self.snapshot()

    def motion_once(self):
        with self._lock:
            command = deepcopy(self._held_velocity)
        if command is None:
            return
        try:
            self._chassis_request("velocity", command, journal=False)
        except WebConsoleError:
            with self._lock:
                self._held_velocity = None
                self._state["chassis"]["velocity"] = {"vx_mm_s": 0, "vy_mm_s": 0, "omega_mrad_s": 0}

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
            self.motion_once()

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
                    self._record_arm_fault(code, repeat=not journal)
                    if journal:
                        self._event("Arm", command, outcome, code)
                    raise WebConsoleError(code) from error
                self._disconnect_arm_state()
                self._fault("arm_transport_failed", "maixcam", code)
                if journal:
                    outcome = outcome or ("UNKNOWN" if command in MOTION_ARM_COMMANDS else "FAULT")
                    self._event("Arm", command, outcome, code)
                raise WebConsoleError(code, 503) from error

    def _record_arm_fault(self, code, repeat=False):
        """Retain errors without re-arming acknowledgement on every status poll."""
        key = "arm_" + code
        with self._lock:
            if not repeat or key not in self._faults:
                self._fault(key, "arm", code)

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
            self.stop_chassis_motion()
        except Exception:
            pass
        self._disconnect_chassis_state()
        self._disconnect_arm_state()
        for thread in self._threads:
            thread.join(timeout=1.0)
