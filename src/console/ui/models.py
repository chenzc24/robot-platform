"""Immutable view-state records shared by the control-console UI."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class Environment(str, Enum):
    """Console execution environments with intentionally different permissions."""

    SIMULATOR = "simulator"
    HARDWARE = "hardware"


class LinkState(str, Enum):
    """Transport or component availability shown independently in the UI."""

    OFFLINE = "offline"
    ONLINE = "online"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class Lifecycle(str, Enum):
    """Traceable command lifecycle states."""

    IDLE = "idle"
    RECEIVED = "received"
    ACCEPTED = "accepted"
    RUNNING = "running"
    DONE = "done"
    REJECTED = "rejected"
    FAULT = "fault"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class VideoState:
    link: LinkState = LinkState.OFFLINE
    overlays_visible: bool = True
    frozen: bool = False
    rotation_degrees: int = 90
    frame_id: int = 0
    fps: float = 0.0
    last_frame_age_ms: Optional[int] = None
    resolution: Optional[Tuple[int, int]] = None
    decode_latency_ms: Optional[int] = None


@dataclass(frozen=True)
class ChassisState:
    link: LinkState = LinkState.OFFLINE
    authenticated: bool = False
    lease_owner: Optional[str] = None
    lease_remaining_ms: Optional[int] = None
    motion_permitted: bool = False
    motion_enabled: bool = False
    manual_unlocked: bool = False
    heartbeat_age_ms: Optional[int] = None
    reported_state: str = "safe idle"
    last_error: str = "none"
    velocity: Tuple[int, int, int] = (0, 0, 0)
    physical_feedback: str = "unavailable"


@dataclass(frozen=True)
class ArmState:
    gateway: LinkState = LinkState.OFFLINE
    uart_lan1: LinkState = LinkState.OFFLINE
    controller: LinkState = LinkState.OFFLINE
    task: Lifecycle = Lifecycle.IDLE
    reported_state: str = "unknown"
    motion_permitted: bool = False
    control_mode: str = "production"
    last_error: str = "none"
    manual_unlocked: bool = False
    last_status_age_ms: Optional[int] = None
    measured_pose: str = "unavailable"


@dataclass(frozen=True)
class EventRecord:
    timestamp_ms: int
    target: str
    command: str
    correlation_id: str
    lifecycle: Lifecycle
    result: str
    detail: str = ""


@dataclass(frozen=True)
class FaultRecord:
    code: str
    severity: str
    source: str
    summary: str
    first_seen_ms: int
    last_seen_ms: int
    acknowledged: bool = False


@dataclass(frozen=True)
class ConsoleState:
    environment: Environment = Environment.SIMULATOR
    scenario: str = "normal"
    video: VideoState = field(default_factory=VideoState)
    chassis: ChassisState = field(default_factory=ChassisState)
    arm: ArmState = field(default_factory=ArmState)
    task_state: str = "idle"
    faults: Tuple[FaultRecord, ...] = ()
