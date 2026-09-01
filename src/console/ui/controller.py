"""Simulator-only state controller for the first control-console UI release."""

from dataclasses import replace
from time import time_ns
from typing import Dict, List

from PySide6.QtCore import QObject, Signal

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


SCENARIOS = (
    ("normal", "Normal"),
    ("video_stale", "Video stale"),
    ("chassis_disconnect", "ESP32 disconnect"),
    ("arm_rejected", "Arm command rejected"),
    ("arm_unknown", "Arm outcome unknown"),
)


class ConsoleController(QObject):
    """Publish immutable state and deterministic synthetic command outcomes.

    This phase intentionally owns no sockets, device clients, media decoder, or
    hardware transport. A later worker-backed adapter will preserve this UI API.
    """

    state_changed = Signal(object)
    event_added = Signal(object)
    faults_changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = ConsoleState()
        self.events: List[EventRecord] = []
        self._faults: Dict[str, FaultRecord] = {}
        self._next_id = 1
        self._active_arm_command = None

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
        self.event_added.emit(event)
        return event

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
        self._sync_faults()

    def _clear_fault(self, code):
        if code in self._faults:
            del self._faults[code]
            self._sync_faults()

    def set_environment(self, environment):
        environment = Environment(environment)
        if environment == self.state.environment:
            return
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
        self._record("Video", "video.snapshot", Lifecycle.REJECTED, "decoder_not_implemented")
        self._raise_fault(
            "snapshot_unavailable",
            "info",
            "video",
            "Snapshots require the Phase B decoded-frame worker.",
        )

    def connect_chassis(self):
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
        self._replace(chassis=ChassisState(reported_state="disconnected"))
        self._record("ESP32", "chassis.disconnect", Lifecycle.DONE, "disconnected")

    def chassis_acquire(self):
        chassis = self.state.chassis
        if chassis.link != LinkState.ONLINE or not chassis.authenticated:
            self._record("ESP32", "chassis.acquire", Lifecycle.REJECTED, "not_connected")
            return False
        self._replace(chassis=replace(chassis, lease_owner="console", lease_remaining_ms=1_000))
        self._record("ESP32", "chassis.acquire", Lifecycle.DONE, "lease_acquired")
        return True

    def chassis_enable(self):
        chassis = self.state.chassis
        if chassis.lease_owner != "console":
            self._record("ESP32", "chassis.enable", Lifecycle.REJECTED, "lease_required")
            return False
        self._replace(chassis=replace(chassis, motion_enabled=True, reported_state="safe idle"))
        self._record("ESP32", "chassis.enable", Lifecycle.DONE, "simulator_enabled")
        return True

    def chassis_disable(self):
        chassis = self.state.chassis
        self._replace(chassis=replace(chassis, motion_enabled=False, manual_unlocked=False, velocity=(0, 0, 0), reported_state="safe idle"))
        self._record("ESP32", "chassis.disable", Lifecycle.DONE, "disabled")

    def chassis_release(self):
        chassis = self.state.chassis
        self._replace(chassis=replace(chassis, lease_owner=None, lease_remaining_ms=None, motion_enabled=False, manual_unlocked=False, velocity=(0, 0, 0)))
        self._record("ESP32", "chassis.release", Lifecycle.DONE, "released")

    def set_chassis_manual_unlock(self, unlocked):
        chassis = self.state.chassis
        allowed = bool(
            unlocked
            and self.state.environment == Environment.SIMULATOR
            and chassis.link == LinkState.ONLINE
            and chassis.lease_owner == "console"
            and chassis.motion_enabled
        )
        self._replace(chassis=replace(chassis, manual_unlocked=allowed))
        self._record("Console", "chassis.manual_unlock", Lifecycle.DONE if allowed or not unlocked else Lifecycle.REJECTED, str(allowed).lower())
        return allowed

    def can_chassis_move(self):
        chassis = self.state.chassis
        return bool(
            self.state.environment == Environment.SIMULATOR
            and chassis.link == LinkState.ONLINE
            and chassis.lease_owner == "console"
            and chassis.motion_enabled
            and chassis.manual_unlocked
            and not any(fault.severity == "fault" for fault in self.state.faults)
        )

    def chassis_velocity(self, vx_mm_s, vy_mm_s, omega_mrad_s):
        if not self.can_chassis_move():
            self._record("ESP32", "chassis.velocity", Lifecycle.REJECTED, "motion_locked")
            return False
        velocity = (int(vx_mm_s), int(vy_mm_s), int(omega_mrad_s))
        state_name = "moving" if velocity != (0, 0, 0) else "safe idle"
        self._replace(chassis=replace(self.state.chassis, velocity=velocity, reported_state=state_name, heartbeat_age_ms=10))
        self._record("ESP32", "chassis.velocity", Lifecycle.RUNNING, "simulated_velocity")
        return True

    def chassis_stop(self):
        if self.state.environment != Environment.SIMULATOR:
            self._simulator_only("ESP32", "chassis.stop")
            return False
        chassis = self.state.chassis
        self._replace(chassis=replace(chassis, velocity=(0, 0, 0), reported_state="safe idle"))
        self._record("ESP32", "chassis.stop", Lifecycle.DONE, "simulated_stop")
        return True

    def connect_arm(self):
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
        self._active_arm_command = None
        self._replace(arm=ArmState())
        self._record("MaixCam", "arm.disconnect", Lifecycle.DONE, "disconnected")

    def _chassis_is_idle(self):
        return self.state.chassis.velocity == (0, 0, 0) and self.state.chassis.reported_state == "safe idle"

    def set_arm_manual_unlock(self, unlocked):
        arm = self.state.arm
        ready = (
            self.state.environment == Environment.SIMULATOR
            and arm.gateway == LinkState.ONLINE
            and arm.uart_lan1 == LinkState.ONLINE
            and arm.controller == LinkState.ONLINE
            and arm.task == Lifecycle.IDLE
            and self._chassis_is_idle()
        )
        allowed = bool(unlocked and ready)
        self._replace(arm=replace(arm, manual_unlocked=allowed))
        self._record("Console", "arm.manual_unlock", Lifecycle.DONE if allowed or not unlocked else Lifecycle.REJECTED, str(allowed).lower())
        return allowed

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
        self._record("Console", "status.recheck", Lifecycle.DONE, "simulator_status")
        if self.state.scenario == "normal":
            for code in ("video_stale", "chassis_link_lost", "hardware_adapter_unavailable", "snapshot_unavailable"):
                self._clear_fault(code)

    def tick(self):
        """Advance visual-only simulator metrics; no device I/O occurs here."""
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
