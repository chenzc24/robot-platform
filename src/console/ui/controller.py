"""Immutable console state controller with simulator and locked runtime bindings."""

from dataclasses import replace
from pathlib import Path
from time import time_ns
from typing import Dict, List

from PySide6.QtCore import QObject, QTimer, Signal

from .models import (
    ArmState,
    ChassisState,
    ConsoleState,
    Environment,
    EventRecord,
    FaultRecord,
    Lifecycle,
    LinkState,
    VideoState,
)
from .runtime import SessionFault, SessionResult
from .status_mapping import StatusMappingError, parse_arm_status, parse_chassis_status


SCENARIOS = (
    ("normal", "Normal"),
    ("video_stale", "Video stale"),
    ("chassis_disconnect", "ESP32 disconnect"),
    ("arm_rejected", "Arm command rejected"),
    ("arm_unknown", "Arm outcome unknown"),
)


class ConsoleController(QObject):
    """Publish immutable UI state and coordinate simulator or runtime adapters."""

    state_changed = Signal(object)
    event_added = Signal(object)
    faults_changed = Signal(object)
    video_frame_ready = Signal(object)

    def __init__(self, runtime=None, parent=None, event_log_path=None):
        super().__init__(parent)
        if runtime is not None and not all(hasattr(runtime, name) for name in ("connect_chassis", "connect_arm", "connect_video")):
            raise TypeError("runtime must provide console runtime operations")
        self.state = ConsoleState()
        self.events: List[EventRecord] = []
        self._faults: Dict[str, FaultRecord] = {}
        self._next_id = 1
        self._active_arm_command = None
        self._held_chassis_velocity = None
        self._event_log_path = Path(event_log_path) if event_log_path else None
        self.runtime = runtime
        self._health_timer = QTimer(self)
        self._health_timer.timeout.connect(self._health_tick)
        self._velocity_refresh_timer = QTimer(self)
        self._velocity_refresh_timer.timeout.connect(self._velocity_refresh_tick)
        if self.runtime is not None:
            self.runtime.chassis_state_changed.connect(self._on_hardware_chassis_state)
            self.runtime.arm_state_changed.connect(self._on_hardware_arm_state)
            self.runtime.video_state_changed.connect(self._on_hardware_video_state)
            self.runtime.result_ready.connect(self._on_hardware_result)
            self.runtime.fault_raised.connect(self._on_hardware_fault)
            self.runtime.frame_ready.connect(self._on_hardware_frame)
        self._initialize_event_log()

    @staticmethod
    def now_ms():
        return time_ns() // 1_000_000

    def _correlation_id(self, target):
        correlation_id = "%s-%04d" % (target, self._next_id)
        self._next_id += 1
        return correlation_id

    def _publish(self, state):
        self.state = state
        self.state_changed.emit(self.state)

    def _replace(self, **changes):
        self._publish(replace(self.state, **changes))

    def _record(self, target, command, lifecycle, result, detail="", correlation_id=None):
        event = EventRecord(
            timestamp_ms=self.now_ms(),
            target=target,
            command=command,
            correlation_id=correlation_id or self._correlation_id(target.lower()),
            lifecycle=lifecycle,
            result=result,
            detail=detail,
        )
        self.events.insert(0, event)
        del self.events[200:]
        self._write_live_log(
            "EVENT",
            timestamp_ms=event.timestamp_ms,
            target=event.target,
            command=event.command,
            correlation_id=event.correlation_id,
            lifecycle=event.lifecycle.value,
            result=event.result,
        )
        self.event_added.emit(event)
        return event

    def _initialize_event_log(self):
        if self._event_log_path is None:
            return
        try:
            self._event_log_path.parent.mkdir(parents=True, exist_ok=True)
            self._event_log_path.write_text("Robot Console live diagnostics\n", encoding="utf-8")
        except OSError:
            self._event_log_path = None

    def _write_live_log(self, kind, **fields):
        if self._event_log_path is None:
            return
        try:
            values = " ".join(
                "%s=%s" % (name, str(value).replace("\r", " ").replace("\n", " "))
                for name, value in fields.items()
            )
            with self._event_log_path.open("a", encoding="utf-8") as handle:
                handle.write("%s %s\n" % (kind, values))
        except OSError:
            pass

    def _sync_faults(self):
        faults = tuple(sorted(self._faults.values(), key=lambda item: item.first_seen_ms))
        self._replace(faults=faults)
        self.faults_changed.emit(faults)

    def _raise_fault(self, code, severity, source, summary):
        now = self.now_ms()
        existing = self._faults.get(code)
        self._faults[code] = FaultRecord(
            code=code,
            severity=severity,
            source=source,
            summary=summary,
            first_seen_ms=existing.first_seen_ms if existing else now,
            last_seen_ms=now,
            acknowledged=existing.acknowledged if existing else False,
        )
        self._write_live_log("FAULT", timestamp_ms=now, code=code, severity=severity, source=source)
        self._sync_faults()

    def _clear_fault(self, code):
        if code in self._faults:
            del self._faults[code]
            self._sync_faults()

    def _clear_recovered_esp32_faults(self):
        recovered = [
            code for code, fault in self._faults.items()
            if fault.source == "esp32" and fault.severity != "unknown"
        ]
        for code in recovered:
            del self._faults[code]
        if recovered:
            self._sync_faults()

    def set_environment(self, environment):
        environment = Environment(environment)
        if environment == self.state.environment:
            return
        if self.state.environment == Environment.HARDWARE and self.runtime is not None:
            self.runtime.disconnect_chassis()
            self.runtime.disconnect_arm()
            self.runtime.disconnect_video()
        self._faults.clear()
        self._active_arm_command = None
        self._replace(
            environment=environment,
            video=VideoState(rotation_degrees=self.state.video.rotation_degrees),
            chassis=ChassisState(),
            arm=ArmState(),
            task_state="idle",
            faults=(),
        )
        self._record("Console", "environment.select", Lifecycle.DONE, environment.value)
        self.faults_changed.emit(())

    def set_scenario(self, scenario):
        if scenario not in dict(SCENARIOS):
            raise ValueError("unsupported simulator scenario")
        self._replace(scenario=scenario)
        self._record("Simulator", "scenario.select", Lifecycle.DONE, scenario)

    def _simulator_only(self, target, command):
        if self.state.environment == Environment.SIMULATOR:
            return True
        self._record(target, command, Lifecycle.REJECTED, "hardware_adapter_unavailable")
        self._raise_fault(
            "hardware_adapter_unavailable",
            "warning",
            "console",
            "Hardware adapters are not included in the simulator release.",
        )
        return False

    def connect_video(self):
        if self.state.environment == Environment.HARDWARE:
            return self._connect_hardware("video")
        if not self._simulator_only("Video", "video.connect"):
            return False
        if self.state.scenario == "video_stale":
            video = replace(
                self.state.video,
                link=LinkState.DEGRADED,
                fps=0.0,
                last_frame_age_ms=3_500,
            )
            self._replace(video=video)
            self._record("Video", "video.connect", Lifecycle.FAULT, "stale_frame")
            self._raise_fault(
                "video_stale",
                "warning",
                "video",
                "The preview is connected but no fresh frame is available.",
            )
            return False
        self._replace(
            video=replace(
                self.state.video,
                link=LinkState.ONLINE,
                fps=20.0,
                last_frame_age_ms=0,
            )
        )
        self._clear_fault("video_stale")
        self._record("Video", "video.connect", Lifecycle.DONE, "simulator_connected")
        return True

    def disconnect_video(self):
        if self.state.environment == Environment.HARDWARE:
            if self.runtime is None:
                return False
            self.runtime.disconnect_video()
            return True
        self._replace(video=replace(self.state.video, link=LinkState.OFFLINE, fps=0.0, last_frame_age_ms=None))
        self._record("Video", "video.disconnect", Lifecycle.DONE, "disconnected")

    def toggle_video_freeze(self):
        self._replace(video=replace(self.state.video, frozen=not self.state.video.frozen))
        self._record("Video", "video.freeze", Lifecycle.DONE, str(self.state.video.frozen).lower())

    def toggle_overlays(self):
        self._replace(video=replace(self.state.video, overlays_visible=not self.state.video.overlays_visible))
        self._record("Video", "video.overlay", Lifecycle.DONE, str(self.state.video.overlays_visible).lower())

    def rotate_video(self):
        rotation = (self.state.video.rotation_degrees + 90) % 360
        self._replace(video=replace(self.state.video, rotation_degrees=rotation))
        self._record("Video", "video.rotate", Lifecycle.DONE, "%d_degrees" % rotation)

    def snapshot(self):
        if self.state.environment == Environment.HARDWARE:
            if self.runtime is not None and self.runtime.save_snapshot():
                return True
            return False
        self._record("Video", "video.snapshot", Lifecycle.REJECTED, "decoder_not_implemented")
        self._raise_fault(
            "snapshot_unavailable",
            "info",
            "video",
            "Snapshots require the Phase B decoded-frame worker.",
        )

    def connect_chassis(self):
        if self.state.environment == Environment.HARDWARE:
            return self._connect_hardware("chassis")
        if not self._simulator_only("ESP32", "chassis.connect"):
            return False
        if self.state.scenario == "chassis_disconnect":
            self._replace(chassis=ChassisState(reported_state="link lost"))
            self._record("ESP32", "chassis.connect", Lifecycle.FAULT, "simulated_disconnect")
            self._raise_fault(
                "chassis_link_lost",
                "fault",
                "chassis",
                "The ESP32 simulator rejected the connection as a link-loss scenario.",
            )
            return False
        chassis = replace(
            self.state.chassis,
            link=LinkState.ONLINE,
            authenticated=True,
            motion_permitted=True,
            health_age_ms=20,
            reported_state="safe idle",
        )
        self._replace(chassis=chassis)
        self._clear_fault("chassis_link_lost")
        self._record("ESP32", "chassis.connect", Lifecycle.DONE, "simulator_connected")
        return True

    def disconnect_chassis(self):
        if self.state.environment == Environment.HARDWARE:
            if self.runtime is None:
                return False
            self._reset_manual_chassis_runtime()
            self.runtime.disconnect_chassis()
            return True
        self._replace(chassis=ChassisState(reported_state="disconnected"))
        self._record("ESP32", "chassis.disconnect", Lifecycle.DONE, "disconnected")

    def chassis_enable(self):
        if self.state.environment == Environment.HARDWARE:
            chassis = self.state.chassis
            if not (
                self._hardware_manual_session_ready()
                and chassis.motion_permitted
                and not chassis.motion_enabled
            ):
                self._record("ESP32", "chassis.enable", Lifecycle.REJECTED, "manual_session_not_ready")
                return False
            return self.runtime.request_chassis_manual("enable")
        chassis = self.state.chassis
        if chassis.link != LinkState.ONLINE or not chassis.authenticated:
            self._record("ESP32", "chassis.enable", Lifecycle.REJECTED, "not_connected")
            return False
        self._replace(chassis=replace(chassis, motion_enabled=True, reported_state="safe idle"))
        self._record("ESP32", "chassis.enable", Lifecycle.DONE, "simulator_enabled")
        return True

    def chassis_disable(self):
        if self.state.environment == Environment.HARDWARE:
            self._held_chassis_velocity = None
            self._velocity_refresh_timer.stop()
            if not self._hardware_manual_session_ready():
                self._record("ESP32", "chassis.disable", Lifecycle.REJECTED, "manual_session_not_ready")
                return False
            return self.runtime.request_chassis_manual("disable")
        chassis = self.state.chassis
        self._replace(chassis=replace(chassis, motion_enabled=False, velocity=(0, 0, 0), reported_state="safe idle"))
        self._record("ESP32", "chassis.disable", Lifecycle.DONE, "disabled")

    def can_chassis_move(self):
        chassis = self.state.chassis
        return bool(
            (self.state.environment == Environment.SIMULATOR or self._hardware_manual_enabled())
            and chassis.link == LinkState.ONLINE
            and chassis.authenticated
            and chassis.motion_permitted
            and chassis.motion_enabled
            and not any(
                fault.severity == "fault" and fault.source in {"chassis", "esp32"}
                for fault in self.state.faults
            )
        )

    def chassis_velocity(self, vx_mm_s, vy_mm_s, omega_mrad_s):
        if not self.can_chassis_move():
            self._record("ESP32", "chassis.velocity", Lifecycle.REJECTED, "motion_locked")
            return False
        velocity = (int(vx_mm_s), int(vy_mm_s), int(omega_mrad_s))
        if self.state.environment == Environment.HARDWARE:
            limits = self.runtime.config.manual_chassis
            if (
                velocity[0] * velocity[0] + velocity[1] * velocity[1] > limits.linear_limit_mm_s * limits.linear_limit_mm_s
                or abs(velocity[2]) > limits.angular_limit_mrad_s
            ):
                self._record("ESP32", "chassis.velocity", Lifecycle.REJECTED, "manual_speed_limited")
                return False
            self._held_chassis_velocity = velocity
            refresh_ms = min(100, max(50, limits.velocity_hold_ms // 3))
            self._velocity_refresh_timer.start(refresh_ms)
            self.runtime.request_chassis_manual(
                "velocity",
                {
                    "vx_mm_s": velocity[0], "vy_mm_s": velocity[1], "omega_mrad_s": velocity[2],
                    "hold_ms": limits.velocity_hold_ms,
                },
            )
            self._replace(chassis=replace(self.state.chassis, velocity=velocity, reported_state="moving"))
            self._record("ESP32", "chassis.velocity", Lifecycle.RUNNING, "hardware_velocity_requested")
            return True
        state_name = "moving" if velocity != (0, 0, 0) else "safe idle"
        self._replace(chassis=replace(self.state.chassis, velocity=velocity, reported_state=state_name, health_age_ms=10))
        self._record("ESP32", "chassis.velocity", Lifecycle.RUNNING, "simulated_velocity")
        return True

    def chassis_stop(self):
        if self.state.environment == Environment.HARDWARE:
            self._held_chassis_velocity = None
            self._velocity_refresh_timer.stop()
            if not self._hardware_manual_session_ready():
                self._record("ESP32", "chassis.stop", Lifecycle.REJECTED, "manual_session_not_ready")
                return False
            self.runtime.request_chassis_manual("stop")
            self._replace(chassis=replace(self.state.chassis, velocity=(0, 0, 0), reported_state="stopping"))
            self._record("ESP32", "chassis.stop", Lifecycle.ACCEPTED, "hardware_stop_requested")
            return True
        if self.state.environment != Environment.SIMULATOR:
            self._simulator_only("ESP32", "chassis.stop")
            return False
        chassis = self.state.chassis
        self._replace(chassis=replace(chassis, velocity=(0, 0, 0), reported_state="safe idle"))
        self._record("ESP32", "chassis.stop", Lifecycle.DONE, "simulated_stop")
        return True

    def _hardware_manual_enabled(self):
        return bool(
            self.runtime is not None
            and getattr(self.runtime, "manual_chassis_enabled", False)
        )

    def _hardware_manual_session_ready(self):
        chassis = self.state.chassis
        return bool(
            self._hardware_manual_enabled()
            and chassis.link == LinkState.ONLINE
            and chassis.authenticated
        )

    def _stop_manual_chassis_timers(self):
        self._held_chassis_velocity = None
        self._health_timer.stop()
        self._velocity_refresh_timer.stop()

    def _reset_manual_chassis_runtime(self):
        self._stop_manual_chassis_timers()

    def _start_health_polling(self):
        if self.state.environment == Environment.HARDWARE and self._hardware_manual_session_ready():
            self._health_timer.start(
                self.runtime.config.manual_chassis.health_interval_ms
            )

    def _health_tick(self):
        if not self._hardware_manual_session_ready():
            self._stop_manual_chassis_timers()
            return
        self.runtime.request_chassis_health()

    def _velocity_refresh_tick(self):
        if not self.can_chassis_move() or self._held_chassis_velocity is None:
            self._held_chassis_velocity = None
            self._velocity_refresh_timer.stop()
            return
        limits = self.runtime.config.manual_chassis
        vx, vy, omega = self._held_chassis_velocity
        self.runtime.request_chassis_manual(
            "velocity",
            {"vx_mm_s": vx, "vy_mm_s": vy, "omega_mrad_s": omega, "hold_ms": limits.velocity_hold_ms},
        )

    def connect_arm(self):
        if self.state.environment == Environment.HARDWARE:
            return self._connect_hardware("arm")
        if not self._simulator_only("MaixCam", "arm.connect"):
            return False
        arm = replace(
            self.state.arm,
            gateway=LinkState.ONLINE,
            uart_lan1=LinkState.ONLINE,
            controller=LinkState.ONLINE,
            task=Lifecycle.IDLE,
            last_status_age_ms=40,
        )
        self._replace(arm=arm)
        self._clear_fault("arm_outcome_unknown")
        self._record("MaixCam", "arm.connect", Lifecycle.DONE, "simulator_ready")
        return True

    def disconnect_arm(self):
        if self.state.environment == Environment.HARDWARE:
            if self.runtime is None:
                return False
            self.runtime.disconnect_arm()
            return True
        self._active_arm_command = None
        self._replace(arm=ArmState())
        self._record("MaixCam", "arm.disconnect", Lifecycle.DONE, "disconnected")

    def _chassis_is_idle(self):
        return self.state.chassis.velocity == (0, 0, 0) and self.state.chassis.reported_state == "safe idle"

    def can_arm_move(self):
        arm = self.state.arm
        return bool(
            arm.gateway == LinkState.ONLINE
            and arm.uart_lan1 == LinkState.ONLINE
            and arm.controller == LinkState.ONLINE
            and arm.task == Lifecycle.IDLE
            and (self.state.environment == Environment.SIMULATOR or arm.motion_permitted)
        )

    def execute_arm(self, command, detail, payload=None):
        if not self.can_arm_move():
            self._record("Arm", command, Lifecycle.REJECTED, "motion_locked", detail)
            return False
        if self.state.environment == Environment.HARDWARE:
            runtime_command = command.removeprefix("arm.")
            self._replace(arm=replace(self.state.arm, task=Lifecycle.RECEIVED))
            self.runtime.request_arm_motion(runtime_command, payload or {})
            return True
        if self.state.scenario == "arm_rejected":
            self._record("Arm", command, Lifecycle.REJECTED, "simulated_rejection", detail)
            return False
        if self.state.scenario == "arm_unknown":
            self._replace(arm=replace(self.state.arm, task=Lifecycle.UNKNOWN, manual_unlocked=False))
            self._record("Arm", command, Lifecycle.UNKNOWN, "simulated_unknown", detail)
            self._raise_fault(
                "arm_outcome_unknown",
                "unknown",
                "arm",
                "The simulator cannot establish whether the arm command completed.",
            )
            return False
        correlation_id = self._correlation_id("arm")
        self._active_arm_command = (correlation_id, command, detail)
        self._replace(arm=replace(self.state.arm, task=Lifecycle.RUNNING))
        self._record("Arm", command, Lifecycle.ACCEPTED, "simulator_accepted", detail, correlation_id)
        self._record("Arm", command, Lifecycle.RUNNING, "simulator_running", detail, correlation_id)
        return True

    def jog_arm_joint(self, joint_index, delta_deg, accel_pct=5, speed_pct=5):
        if isinstance(joint_index, bool) or not isinstance(joint_index, int) or not 0 <= joint_index < 6:
            raise ValueError("invalid_joint_index")
        delta = [0.0] * 6
        delta[joint_index] = float(delta_deg)
        detail = "J%d %+.3f deg" % (joint_index + 1, float(delta_deg))
        return self.execute_arm(
            "arm.jog_joint", detail,
            {"joint_delta_deg": delta, "accel_pct": int(accel_pct), "speed_pct": int(speed_pct)},
        )

    def jog_arm_xyz(self, axis_index, delta_mm, accel_pct=5, speed_pct=5, user=0, tool=0):
        if isinstance(axis_index, bool) or not isinstance(axis_index, int) or not 0 <= axis_index < 3:
            raise ValueError("invalid_axis_index")
        delta = [0.0] * 3
        delta[axis_index] = float(delta_mm)
        detail = "%s %+.3f mm" % ("XYZ"[axis_index], float(delta_mm))
        return self.execute_arm(
            "arm.jog_xyz", detail,
            {"translation_mm": delta, "user": int(user), "tool": int(tool),
             "accel_pct": int(accel_pct), "speed_pct": int(speed_pct)},
        )

    def complete_arm_command(self):
        if self.state.arm.task != Lifecycle.RUNNING:
            return False
        correlation_id, command, detail = self._active_arm_command
        self._active_arm_command = None
        self._replace(arm=replace(self.state.arm, task=Lifecycle.IDLE))
        self._record("Arm", command, Lifecycle.DONE, "simulator_done", detail, correlation_id)
        return True

    def acknowledge_fault(self, code):
        fault = self._faults.get(code)
        if fault is None:
            return False
        self._faults[code] = replace(fault, acknowledged=True, last_seen_ms=self.now_ms())
        self._sync_faults()
        self._record("Console", "fault.acknowledge", Lifecycle.DONE, code)
        return True

    def recheck(self):
        if self.state.environment == Environment.HARDWARE:
            if self.runtime is None:
                self._simulator_only("Console", "status.recheck")
                return False
            if self.state.chassis.link == LinkState.ONLINE:
                self.runtime.request_chassis_status()
            if self.state.arm.gateway == LinkState.ONLINE:
                self.runtime.request_arm_status()
            self._record("Console", "status.recheck", Lifecycle.ACCEPTED, "hardware_status_requested")
            return True
        self._record("Console", "status.recheck", Lifecycle.DONE, "simulator_status")
        if self.state.scenario == "normal":
            for code in ("video_stale", "chassis_link_lost", "hardware_adapter_unavailable", "snapshot_unavailable"):
                self._clear_fault(code)
        return True

    def tick(self):
        """Advance visual-only simulator metrics; no device I/O occurs here."""
        if self.state.environment != Environment.SIMULATOR:
            return
        video = self.state.video
        chassis = self.state.chassis
        arm = self.state.arm
        changed = False
        if video.link == LinkState.ONLINE and not video.frozen:
            video = replace(video, frame_id=video.frame_id + 1, last_frame_age_ms=0)
            changed = True
        if chassis.link == LinkState.ONLINE:
            chassis = replace(chassis, health_age_ms=20)
            changed = True
        if arm.gateway == LinkState.ONLINE:
            arm = replace(arm, last_status_age_ms=40)
            changed = True
        if changed:
            self._replace(video=video, chassis=chassis, arm=arm)

    def _connect_hardware(self, target):
        if self.runtime is None:
            self._simulator_only(target.title(), "%s.connect" % target)
            return False
        operations = {
            "chassis": self.runtime.connect_chassis,
            "arm": self.runtime.connect_arm,
            "video": self.runtime.connect_video,
        }
        accepted = operations[target]()
        if accepted:
            labels = {"chassis": ("ESP32", "chassis.connect"), "arm": ("MaixCam", "arm.connect"), "video": ("Video", "video.connect")}
            label, command = labels[target]
            self._record(label, command, Lifecycle.ACCEPTED, "hardware_connection_requested")
        return accepted

    def _on_hardware_chassis_state(self, state):
        if self.state.environment != Environment.HARDWARE:
            return
        if state == "online":
            chassis = replace(self.state.chassis, link=LinkState.ONLINE, authenticated=True, health_age_ms=None, reported_state="status pending")
            self._replace(chassis=chassis)
            self.runtime.request_chassis_status()
        elif state == "connecting":
            self._replace(chassis=replace(self.state.chassis, link=LinkState.DEGRADED, reported_state="connecting"))
        else:
            self._reset_manual_chassis_runtime()
            self._replace(chassis=ChassisState(reported_state="disconnected"))

    def _on_hardware_arm_state(self, state):
        if self.state.environment != Environment.HARDWARE:
            return
        if state == "online":
            arm = replace(self.state.arm, gateway=LinkState.ONLINE, uart_lan1=LinkState.UNKNOWN, controller=LinkState.UNKNOWN, last_status_age_ms=None)
            self._replace(arm=arm)
            self.runtime.request_arm_status()
        elif state == "connecting":
            self._replace(arm=replace(self.state.arm, gateway=LinkState.DEGRADED))
        else:
            self._replace(arm=ArmState())

    def _on_hardware_video_state(self, state):
        if self.state.environment != Environment.HARDWARE:
            return
        mapping = {"online": LinkState.ONLINE, "connecting": LinkState.DEGRADED, "degraded": LinkState.DEGRADED, "offline": LinkState.OFFLINE}
        link = mapping.get(state, LinkState.UNKNOWN)
        self._replace(video=replace(self.state.video, link=link, fps=0.0 if link != LinkState.ONLINE else self.state.video.fps))

    def _on_hardware_result(self, result):
        if self.state.environment != Environment.HARDWARE or not isinstance(result, SessionResult):
            return
        if result.command != "ping":
            self._record(result.target, result.command, result.lifecycle, result.code)
        if result.target == "ESP32" and result.command == "status" and result.lifecycle == Lifecycle.DONE:
            self._apply_chassis_status(result.payload)
        elif result.target == "ESP32" and result.command in {"enable", "stop", "disable"}:
            if result.lifecycle == Lifecycle.DONE:
                if result.command == "disable":
                    self._held_chassis_velocity = None
                    self._velocity_refresh_timer.stop()
                self.runtime.request_chassis_status()
        elif result.target == "ESP32" and result.command == "velocity" and result.lifecycle != Lifecycle.DONE:
            self._held_chassis_velocity = None
            self._velocity_refresh_timer.stop()
            self._replace(chassis=replace(self.state.chassis, velocity=(0, 0, 0), reported_state="enabled stopped"))
        elif result.target == "ESP32" and result.command == "ping" and result.lifecycle == Lifecycle.DONE:
            self._replace(chassis=replace(self.state.chassis, health_age_ms=0))
        if result.target == "MaixCam" and result.command in {"move_joint", "move_linear", "jog_joint", "jog_xyz", "gripper"}:
            self._apply_hardware_arm_motion_result(result)
        elif result.target == "MaixCam" and result.command == "status" and result.lifecycle == Lifecycle.DONE:
            self._apply_arm_status(result.payload)

    def _apply_hardware_arm_motion_result(self, result):
        """Record returned MaixCam lifecycle evidence without fabricating pose proof."""
        if result.lifecycle == Lifecycle.DONE and isinstance(result.payload, (list, tuple)):
            for response in result.payload:
                if not isinstance(response, dict):
                    continue
                lifecycle_text = response.get("lifecycle")
                try:
                    lifecycle = Lifecycle(lifecycle_text.lower())
                except (AttributeError, ValueError):
                    continue
                payload = response.get("payload") or {}
                code = payload.get("error_code") or "downstream_%s" % lifecycle.value
                self._record("Arm", "arm.%s" % result.command, lifecycle, code)
            terminal = result.payload[-1] if result.payload else {}
            terminal_state = terminal.get("lifecycle") if isinstance(terminal, dict) else ""
            task = Lifecycle.IDLE if terminal_state == "DONE" else Lifecycle.FAULT
            self._replace(arm=replace(self.state.arm, task=task))
            self.runtime.request_arm_status()
            return
        task = Lifecycle.IDLE if result.lifecycle in {Lifecycle.DONE, Lifecycle.REJECTED} else result.lifecycle
        self._replace(arm=replace(self.state.arm, task=task))
        self.runtime.request_arm_status()

    def _apply_chassis_status(self, payload):
        try:
            status = parse_chassis_status(payload)
        except StatusMappingError as error:
            self._raise_fault(error.args[0], "fault", "esp32", "ESP32 returned an invalid status payload.")
            return
        chassis = replace(
            self.state.chassis,
            authenticated=status.authenticated,
            motion_permitted=status.motion_permitted,
            motion_enabled=status.motion_enabled,
            health_age_ms=0,
            reported_state=status.chassis_state.replace("_", " "),
            last_error=status.last_error,
        )
        if not (chassis.motion_enabled and chassis.motion_permitted):
            chassis = replace(chassis, velocity=(0, 0, 0))
            self._held_chassis_velocity = None
            self._velocity_refresh_timer.stop()
        self._replace(chassis=chassis)
        self._start_health_polling()
        if status.service_state == "ready" and status.last_error == "none":
            self._clear_recovered_esp32_faults()

    def _apply_arm_status(self, payload):
        try:
            status = parse_arm_status(payload)
        except StatusMappingError as error:
            self._raise_fault(error.args[0], "fault", "arm", "MaixCam returned an invalid arm status payload.")
            return
        controller_link = LinkState.ONLINE if status.service_state == "ready" else LinkState.DEGRADED
        task = {
            "ready": Lifecycle.IDLE,
            "running": Lifecycle.RUNNING,
            "fault": Lifecycle.FAULT,
        }[status.service_state]
        arm = replace(
            self.state.arm,
            uart_lan1=LinkState.ONLINE,
            controller=controller_link,
            task=task,
            reported_state=status.service_state,
            motion_permitted=status.motion_permitted,
            control_mode=status.control_mode,
            last_error=status.last_error,
            last_status_age_ms=0,
        )
        self._replace(arm=arm)

    def _on_hardware_fault(self, fault):
        if self.state.environment != Environment.HARDWARE or not isinstance(fault, SessionFault):
            return
        severity = "unknown" if fault.state_changing else "fault"
        self._record(fault.target, "runtime.%s" % fault.code, Lifecycle.UNKNOWN if fault.state_changing else Lifecycle.FAULT, fault.code)
        self._raise_fault(fault.code, severity, fault.target.lower(), fault.detail)

    def _on_hardware_frame(self, frame):
        if self.state.environment != Environment.HARDWARE:
            return
        self._replace(
            video=replace(
                self.state.video,
                link=LinkState.ONLINE,
                frame_id=frame.frame_id,
                fps=frame.fps,
                last_frame_age_ms=0,
                resolution=(frame.image.width(), frame.image.height()),
                decode_latency_ms=frame.decode_latency_ms,
            )
        )
        self.video_frame_ready.emit(frame)
