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
        self._manual_chassis_transition = None
        self._manual_chassis_pending_command = None
        self._event_log_path = Path(event_log_path) if event_log_path else None
        self.runtime = runtime
        self._lease_heartbeat_timer = QTimer(self)
        self._lease_heartbeat_timer.timeout.connect(self._lease_heartbeat_tick)
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
            heartbeat_age_ms=20,
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

    def chassis_manual_transition(self):
        return self._manual_chassis_transition

    def can_start_chassis_manual(self):
        chassis = self.state.chassis
        return bool(
            self._manual_chassis_transition is None
            and (self.state.environment == Environment.SIMULATOR or self._hardware_manual_enabled())
            and chassis.link == LinkState.ONLINE
            and chassis.authenticated
            and chassis.lease_owner in (None, self.chassis_lease_owner_id())
            and not chassis.manual_unlocked
        )

    def can_end_chassis_manual(self):
        chassis = self.state.chassis
        return bool(
            self._manual_chassis_transition is None
            and chassis.link == LinkState.ONLINE
            and (
                chassis.lease_owner == self.chassis_lease_owner_id()
                or chassis.motion_enabled
                or chassis.manual_unlocked
            )
        )

    def start_chassis_manual(self):
        """Acquire and enable the attended manual session from one operator action."""
        if not self.can_start_chassis_manual():
            self._record("ESP32", "chassis.manual_start", Lifecycle.REJECTED, "manual_session_not_ready")
            return False
        if self.state.environment == Environment.SIMULATOR:
            if self.state.chassis.lease_owner is None and not self.chassis_acquire():
                return False
            if not self.state.chassis.motion_enabled and not self.chassis_enable():
                return False
            return self.set_chassis_manual_unlock(True)
        self._manual_chassis_transition = "starting"
        self._record("ESP32", "chassis.manual_start", Lifecycle.ACCEPTED, "starting")
        self._publish(self.state)
        return self._advance_chassis_manual_start()

    def _advance_chassis_manual_start(self):
        if self._manual_chassis_transition != "starting" or self._manual_chassis_pending_command:
            return False
        chassis = self.state.chassis
        owner_id = self.chassis_lease_owner_id()
        if not self._hardware_manual_session_ready() or chassis.lease_owner not in (None, owner_id):
            self._finish_chassis_manual_transition(Lifecycle.REJECTED, "manual_session_not_ready")
            return False
        if chassis.lease_owner is None:
            self._manual_chassis_pending_command = "acquire"
            accepted = self.runtime.request_chassis_manual(
                "acquire", {"lease_ms": self.runtime.config.manual_chassis.lease_ms}
            )
            if not accepted:
                self._manual_chassis_pending_command = None
                self._finish_chassis_manual_transition(Lifecycle.REJECTED, "motion_not_admitted")
            return accepted
        self._start_lease_heartbeat()
        if not chassis.motion_permitted:
            self._finish_chassis_manual_transition(Lifecycle.REJECTED, "motion_disabled")
            return False
        if not chassis.motion_enabled:
            self._manual_chassis_pending_command = "enable"
            accepted = self.runtime.request_chassis_manual("enable")
            if not accepted:
                self._manual_chassis_pending_command = None
                self._finish_chassis_manual_transition(Lifecycle.REJECTED, "motion_not_admitted")
            return accepted
        self._replace(chassis=replace(chassis, manual_unlocked=True, velocity=(0, 0, 0)))
        self._finish_chassis_manual_transition(Lifecycle.DONE, "ready")
        return True

    def end_chassis_manual(self):
        """Stop, disable, and release the attended session from one operator action."""
        if not self.can_end_chassis_manual():
            self._record("ESP32", "chassis.manual_end", Lifecycle.REJECTED, "manual_session_not_active")
            return False
        if self.state.environment == Environment.SIMULATOR:
            self.chassis_stop()
            self.chassis_disable()
            self.chassis_release()
            return True
        self._stop_manual_chassis_timers()
        self._manual_chassis_transition = "ending"
        self._manual_chassis_pending_command = "stop"
        self._replace(chassis=replace(self.state.chassis, manual_unlocked=False, velocity=(0, 0, 0), reported_state="stopping"))
        self._record("ESP32", "chassis.manual_end", Lifecycle.ACCEPTED, "stopping")
        accepted = self.runtime.request_chassis_manual("stop")
        if not accepted:
            self._finish_chassis_manual_transition(Lifecycle.REJECTED, "motion_not_admitted")
        return accepted

    def _finish_chassis_manual_transition(self, lifecycle, code):
        transition = self._manual_chassis_transition
        self._manual_chassis_transition = None
        self._manual_chassis_pending_command = None
        self._record("ESP32", "chassis.manual_%s" % ("start" if transition == "starting" else "end"), lifecycle, code)
        self._publish(self.state)

    def chassis_acquire(self):
        if self.state.environment == Environment.HARDWARE:
            chassis = self.state.chassis
            if not self._hardware_manual_session_ready() or chassis.lease_owner is not None:
                self._record("ESP32", "chassis.acquire", Lifecycle.REJECTED, "manual_session_not_ready")
                return False
            return self.runtime.request_chassis_manual(
                "acquire", {"lease_ms": self.runtime.config.manual_chassis.lease_ms}
            )
        chassis = self.state.chassis
        if chassis.link != LinkState.ONLINE or not chassis.authenticated:
            self._record("ESP32", "chassis.acquire", Lifecycle.REJECTED, "not_connected")
            return False
        self._replace(chassis=replace(chassis, lease_owner="console", lease_remaining_ms=1_000))
        self._record("ESP32", "chassis.acquire", Lifecycle.DONE, "lease_acquired")
        return True

    def chassis_enable(self):
        if self.state.environment == Environment.HARDWARE:
            chassis = self.state.chassis
            if not (
                self._hardware_manual_session_ready()
                and chassis.lease_owner == self.chassis_lease_owner_id()
                and chassis.motion_permitted
                and not chassis.motion_enabled
            ):
                self._record("ESP32", "chassis.enable", Lifecycle.REJECTED, "manual_session_not_ready")
                return False
            return self.runtime.request_chassis_manual("enable")
        chassis = self.state.chassis
        if chassis.lease_owner != "console":
            self._record("ESP32", "chassis.enable", Lifecycle.REJECTED, "lease_required")
            return False
        self._replace(chassis=replace(chassis, motion_enabled=True, reported_state="safe idle"))
        self._record("ESP32", "chassis.enable", Lifecycle.DONE, "simulator_enabled")
        return True

    def chassis_disable(self):
        if self.state.environment == Environment.HARDWARE:
            self._held_chassis_velocity = None
            if not self._hardware_manual_session_ready():
                self._record("ESP32", "chassis.disable", Lifecycle.REJECTED, "manual_session_not_ready")
                return False
            return self.runtime.request_chassis_manual("disable")
        chassis = self.state.chassis
        self._replace(chassis=replace(chassis, motion_enabled=False, manual_unlocked=False, velocity=(0, 0, 0), reported_state="safe idle"))
        self._record("ESP32", "chassis.disable", Lifecycle.DONE, "disabled")

    def chassis_release(self):
        if self.state.environment == Environment.HARDWARE:
            self._stop_manual_chassis_timers()
            if not self._hardware_manual_session_ready():
                self._record("ESP32", "chassis.release", Lifecycle.REJECTED, "manual_session_not_ready")
                return False
            return self.runtime.request_chassis_manual("release")
        chassis = self.state.chassis
        self._replace(chassis=replace(chassis, lease_owner=None, lease_remaining_ms=None, motion_enabled=False, manual_unlocked=False, velocity=(0, 0, 0)))
        self._record("ESP32", "chassis.release", Lifecycle.DONE, "released")

    def set_chassis_manual_unlock(self, unlocked):
        chassis = self.state.chassis
        if self.state.environment == Environment.HARDWARE:
            allowed = bool(
                unlocked
                and self._hardware_manual_enabled()
                and chassis.link == LinkState.ONLINE
                and chassis.authenticated
                and chassis.lease_owner == self.chassis_lease_owner_id()
                and chassis.motion_permitted
                and chassis.motion_enabled
            )
            if allowed:
                self._replace(chassis=replace(chassis, manual_unlocked=True))
                self._start_lease_heartbeat()
                self.runtime.request_chassis_manual(
                    "heartbeat", {"lease_ms": self.runtime.config.manual_chassis.lease_ms}
                )
            else:
                self._held_chassis_velocity = None
                self._velocity_refresh_timer.stop()
                self._replace(chassis=replace(chassis, manual_unlocked=False, velocity=(0, 0, 0)))
                if self._hardware_manual_session_ready():
                    self.runtime.request_chassis_manual("stop")
            self._record("Console", "chassis.manual_unlock", Lifecycle.DONE if allowed or not unlocked else Lifecycle.REJECTED, str(allowed).lower())
            return allowed
        allowed = bool(
            unlocked
            and self.state.environment == Environment.SIMULATOR
            and chassis.link == LinkState.ONLINE
            and chassis.lease_owner == self.chassis_lease_owner_id()
            and chassis.motion_enabled
        )
        self._replace(chassis=replace(chassis, manual_unlocked=allowed))
        self._record("Console", "chassis.manual_unlock", Lifecycle.DONE if allowed or not unlocked else Lifecycle.REJECTED, str(allowed).lower())
        return allowed

    def can_chassis_move(self):
        chassis = self.state.chassis
        return bool(
            (self.state.environment == Environment.SIMULATOR or self._hardware_manual_enabled())
            and chassis.link == LinkState.ONLINE
            and chassis.lease_owner == self.chassis_lease_owner_id()
            and chassis.motion_enabled
            and chassis.manual_unlocked
            and not any(fault.severity == "fault" for fault in self.state.faults)
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
        self._replace(chassis=replace(self.state.chassis, velocity=velocity, reported_state=state_name, heartbeat_age_ms=10))
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

    def chassis_lease_owner_id(self):
        """Return the owner name that the selected environment must report."""
        if self.state.environment == Environment.HARDWARE and self.runtime is not None:
            chassis = getattr(getattr(self.runtime, "config", None), "chassis", None)
            client_id = getattr(chassis, "client_id", None)
            if isinstance(client_id, str) and client_id:
                return client_id
        return "console"

    def _hardware_manual_session_ready(self):
        chassis = self.state.chassis
        return bool(
            self._hardware_manual_enabled()
            and chassis.link == LinkState.ONLINE
            and chassis.authenticated
        )

    def _hardware_manual_lease_owned(self):
        chassis = self.state.chassis
        return bool(
            self._hardware_manual_session_ready()
            and chassis.lease_owner == self.chassis_lease_owner_id()
        )

    def _stop_manual_chassis_timers(self):
        self._held_chassis_velocity = None
        self._lease_heartbeat_timer.stop()
        self._velocity_refresh_timer.stop()

    def _reset_manual_chassis_runtime(self):
        self._stop_manual_chassis_timers()
        self._manual_chassis_transition = None
        self._manual_chassis_pending_command = None

    def _start_lease_heartbeat(self):
        interval = self.runtime.config.manual_chassis.heartbeat_interval_ms
        self._lease_heartbeat_timer.start(interval)

    def _lease_heartbeat_tick(self):
        if not self._hardware_manual_lease_owned():
            self._stop_manual_chassis_timers()
            return
        limits = self.runtime.config.manual_chassis
        self.runtime.request_chassis_manual("heartbeat", {"lease_ms": limits.lease_ms})

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

    def set_arm_manual_unlock(self, unlocked):
        arm = self.state.arm
        simulator_ready = (
            self.state.environment == Environment.SIMULATOR
            and arm.gateway == LinkState.ONLINE
            and arm.uart_lan1 == LinkState.ONLINE
            and arm.controller == LinkState.ONLINE
            and arm.task == Lifecycle.IDLE
            and self._chassis_is_idle()
        )
        allowed = bool(unlocked and (simulator_ready or self._hardware_arm_l3_ready()))
        self._replace(arm=replace(arm, manual_unlocked=allowed))
        self._record("Console", "arm.manual_unlock", Lifecycle.DONE if allowed or not unlocked else Lifecycle.REJECTED, str(allowed).lower())
        return allowed

    def _hardware_arm_l3_ready(self):
        """Gate the one reviewed test action; it is not a generic arm enable."""
        arm, chassis = self.state.arm, self.state.chassis
        blocking_fault = any(
            fault.severity in ("fault", "unknown") and fault.source in {"arm", "maixcam", "esp32"}
            for fault in self.state.faults
        )
        return bool(
            self.state.environment == Environment.HARDWARE
            and self.runtime is not None
            and arm.gateway == LinkState.ONLINE
            and arm.uart_lan1 == LinkState.ONLINE
            and arm.controller == LinkState.ONLINE
            and arm.task == Lifecycle.IDLE
            and arm.motion_permitted
            and chassis.link == LinkState.ONLINE
            and chassis.reported_state == "safe idle"
            and not blocking_fault
        )

    def can_hardware_arm_l3_test(self):
        return bool(self._hardware_arm_l3_ready() and self.state.arm.manual_unlocked)

    def execute_hardware_arm_l3_test(self):
        if not self.can_hardware_arm_l3_test():
            self._record("Arm", "arm.l3_j1_cycle", Lifecycle.REJECTED, "l3_test_locked")
            return False
        self._replace(arm=replace(self.state.arm, task=Lifecycle.RECEIVED, manual_unlocked=False))
        self.runtime.request_arm_l3_j1_cycle()
        return True

    def can_arm_move(self):
        arm = self.state.arm
        return bool(
            self.state.environment == Environment.SIMULATOR
            and arm.gateway == LinkState.ONLINE
            and arm.uart_lan1 == LinkState.ONLINE
            and arm.controller == LinkState.ONLINE
            and arm.task == Lifecycle.IDLE
            and arm.manual_unlocked
            and self._chassis_is_idle()
            and not any(fault.severity in ("fault", "unknown") for fault in self.state.faults)
        )

    def execute_arm(self, command, detail):
        if not self.can_arm_move():
            self._record("Arm", command, Lifecycle.REJECTED, "motion_locked", detail)
            return False
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
            lease_remaining = max(0, (chassis.lease_remaining_ms or 0) - 100) if chassis.lease_owner else None
            chassis = replace(chassis, lease_remaining_ms=lease_remaining, heartbeat_age_ms=20)
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
            chassis = replace(self.state.chassis, link=LinkState.ONLINE, authenticated=True, heartbeat_age_ms=None, reported_state="status pending")
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
        if result.command != "heartbeat":
            self._record(result.target, result.command, result.lifecycle, result.code)
        if result.target == "ESP32" and result.command == "status" and result.lifecycle == Lifecycle.DONE:
            self._apply_chassis_status(result.payload)
        elif result.target == "ESP32" and result.command in {"acquire", "enable", "stop", "disable", "release"}:
            if result.lifecycle == Lifecycle.DONE:
                if result.command == self._manual_chassis_pending_command:
                    self._manual_chassis_pending_command = None
                if self._manual_chassis_transition == "ending":
                    next_command = {"stop": "disable", "disable": "release"}.get(result.command)
                    if next_command is not None:
                        self._manual_chassis_pending_command = next_command
                        self.runtime.request_chassis_manual(next_command)
                    else:
                        self._finish_chassis_manual_transition(Lifecycle.DONE, "ended")
                        self.runtime.request_chassis_status()
                else:
                    self.runtime.request_chassis_status()
            else:
                if result.command == self._manual_chassis_pending_command:
                    self._manual_chassis_pending_command = None
                if self._manual_chassis_transition is not None:
                    self._finish_chassis_manual_transition(result.lifecycle, result.code)
                if result.command in {"disable", "release"}:
                    self._stop_manual_chassis_timers()
        elif result.target == "ESP32" and result.command == "velocity" and result.lifecycle != Lifecycle.DONE:
            self._held_chassis_velocity = None
            self._velocity_refresh_timer.stop()
            self._replace(chassis=replace(self.state.chassis, velocity=(0, 0, 0), reported_state="enabled stopped"))
        elif result.target == "ESP32" and result.command == "heartbeat" and result.lifecycle != Lifecycle.DONE:
            self._stop_manual_chassis_timers()
            self._replace(chassis=replace(self.state.chassis, manual_unlocked=False, velocity=(0, 0, 0)))
        if result.target == "MaixCam" and result.command == "l3_j1_cycle":
            self._apply_hardware_arm_l3_result(result)
        elif result.target == "MaixCam" and result.command == "status" and result.lifecycle == Lifecycle.DONE:
            self._apply_arm_status(result.payload)

    def _apply_hardware_arm_l3_result(self, result):
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
                self._record("Arm", "arm.l3_j1_cycle", lifecycle, code)
            terminal = result.payload[-1] if result.payload else {}
            terminal_state = terminal.get("lifecycle") if isinstance(terminal, dict) else ""
            task = Lifecycle.IDLE if terminal_state == "DONE" else Lifecycle.FAULT
            self._replace(arm=replace(self.state.arm, task=task, manual_unlocked=False))
            self.runtime.request_arm_status()
            return
        self._replace(arm=replace(self.state.arm, task=Lifecycle.IDLE, manual_unlocked=False))
        self.runtime.request_arm_status()

    def _apply_chassis_status(self, payload):
        try:
            status = parse_chassis_status(payload)
        except StatusMappingError as error:
            self._raise_fault(error.args[0], "fault", "esp32", "ESP32 returned an invalid status payload.")
            if self._manual_chassis_transition == "starting":
                self._finish_chassis_manual_transition(Lifecycle.REJECTED, error.args[0])
            return
        owner = status.lease_owner if status.lease_active else None
        chassis = replace(
            self.state.chassis,
            authenticated=status.authenticated,
            lease_owner=owner,
            lease_remaining_ms=status.lease_remaining_ms if owner else None,
            motion_permitted=status.motion_permitted,
            motion_enabled=status.motion_enabled,
            heartbeat_age_ms=0,
            reported_state=status.chassis_state.replace("_", " "),
            last_error=status.last_error,
        )
        if chassis.lease_owner != self.chassis_lease_owner_id():
            chassis = replace(chassis, manual_unlocked=False, velocity=(0, 0, 0))
            self._stop_manual_chassis_timers()
        else:
            if not (chassis.motion_enabled and chassis.motion_permitted):
                chassis = replace(chassis, manual_unlocked=False, velocity=(0, 0, 0))
                self._held_chassis_velocity = None
                self._velocity_refresh_timer.stop()
            self._start_lease_heartbeat()
        self._replace(chassis=chassis)
        if status.service_state == "ready" and status.last_error == "none":
            self._clear_recovered_esp32_faults()
        if self._manual_chassis_transition == "starting":
            self._advance_chassis_manual_start()

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
