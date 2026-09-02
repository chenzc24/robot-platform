"""Secret-free local configuration loading for the control-console runtime."""

import json
from dataclasses import dataclass
from pathlib import Path


class RuntimeConfigError(ValueError):
    """A local runtime configuration is absent or structurally unsafe."""


@dataclass(frozen=True)
class EndpointConfig:
    host: str
    port: int
    connect_timeout_seconds: float

    @property
    def complete(self):
        return bool(self.host and 1024 <= self.port <= 65535 and self.connect_timeout_seconds > 0)


@dataclass(frozen=True)
class ChassisConfig(EndpointConfig):
    client_id: str
    credential_env: str


@dataclass(frozen=True)
class ManualChassisConfig:
    enabled: bool
    lease_ms: int
    heartbeat_interval_ms: int
    velocity_hold_ms: int
    linear_limit_mm_s: int
    angular_limit_mrad_s: int


@dataclass(frozen=True)
class ArmConfig(EndpointConfig):
    session_id: str


@dataclass(frozen=True)
class VideoConfig:
    rtsp_url: str
    connect_timeout_seconds: float
    snapshot_directory: str

    @property
    def complete(self):
        return bool(self.rtsp_url and self.connect_timeout_seconds > 0)


@dataclass(frozen=True)
class RuntimeConfig:
    chassis: ChassisConfig
    manual_chassis: ManualChassisConfig
    arm: ArmConfig
    video: VideoConfig


def _mapping(value, field):
    if not isinstance(value, dict):
        raise RuntimeConfigError("%s must be an object" % field)
    return value


def _string(value, field, allow_empty=False):
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise RuntimeConfigError("%s must be a non-empty string" % field)
    return value.strip()


def _port(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 65535:
        raise RuntimeConfigError("%s must be an integer in 0..65535" % field)
    return value


def _timeout(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise RuntimeConfigError("%s must be positive" % field)
    return float(value)


def _positive_int(value, field, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise RuntimeConfigError("%s must be an integer in %d..%d" % (field, low, high))
    return value


def _boolean(value, field):
    if not isinstance(value, bool):
        raise RuntimeConfigError("%s must be a boolean" % field)
    return value


def load_runtime_config(path):
    """Load an explicit local JSON configuration without logging its contents."""
    source = Path(path)
    if not source.is_file():
        raise RuntimeConfigError("local configuration is unavailable")
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeConfigError("local configuration cannot be read") from error
    if set(raw) != {"schema_version", "chassis", "manual_chassis", "arm", "video"}:
        raise RuntimeConfigError("unexpected configuration fields")
    if raw["schema_version"] != 1:
        raise RuntimeConfigError("unsupported configuration schema")
    chassis = _mapping(raw["chassis"], "chassis")
    manual_chassis = _mapping(raw["manual_chassis"], "manual_chassis")
    arm = _mapping(raw["arm"], "arm")
    video = _mapping(raw["video"], "video")
    if set(chassis) != {"host", "port", "client_id", "credential_env", "connect_timeout_seconds"}:
        raise RuntimeConfigError("unexpected chassis configuration fields")
    if set(manual_chassis) != {"enabled", "lease_ms", "heartbeat_interval_ms", "velocity_hold_ms", "linear_limit_mm_s", "angular_limit_mrad_s"}:
        raise RuntimeConfigError("unexpected manual chassis configuration fields")
    if set(arm) != {"host", "port", "session_id", "connect_timeout_seconds"}:
        raise RuntimeConfigError("unexpected arm configuration fields")
    if set(video) != {"rtsp_url", "connect_timeout_seconds", "snapshot_directory"}:
        raise RuntimeConfigError("unexpected video configuration fields")
    return RuntimeConfig(
        chassis=ChassisConfig(
            host=_string(chassis["host"], "chassis.host", allow_empty=True),
            port=_port(chassis["port"], "chassis.port"),
            client_id=_string(chassis["client_id"], "chassis.client_id"),
            credential_env=_string(chassis["credential_env"], "chassis.credential_env"),
            connect_timeout_seconds=_timeout(chassis["connect_timeout_seconds"], "chassis.connect_timeout_seconds"),
        ),
        manual_chassis=ManualChassisConfig(
            enabled=_boolean(manual_chassis["enabled"], "manual_chassis.enabled"),
            lease_ms=_positive_int(manual_chassis["lease_ms"], "manual_chassis.lease_ms", 500, 10_000),
            heartbeat_interval_ms=_positive_int(manual_chassis["heartbeat_interval_ms"], "manual_chassis.heartbeat_interval_ms", 50, 1_000),
            velocity_hold_ms=_positive_int(manual_chassis["velocity_hold_ms"], "manual_chassis.velocity_hold_ms", 50, 500),
            linear_limit_mm_s=_positive_int(manual_chassis["linear_limit_mm_s"], "manual_chassis.linear_limit_mm_s", 1, 600),
            angular_limit_mrad_s=_positive_int(manual_chassis["angular_limit_mrad_s"], "manual_chassis.angular_limit_mrad_s", 1, 800),
        ),
        arm=ArmConfig(
            host=_string(arm["host"], "arm.host", allow_empty=True),
            port=_port(arm["port"], "arm.port"),
            session_id=_string(arm["session_id"], "arm.session_id"),
            connect_timeout_seconds=_timeout(arm["connect_timeout_seconds"], "arm.connect_timeout_seconds"),
        ),
        video=VideoConfig(
            rtsp_url=_string(video["rtsp_url"], "video.rtsp_url", allow_empty=True),
            connect_timeout_seconds=_timeout(video["connect_timeout_seconds"], "video.connect_timeout_seconds"),
            snapshot_directory=_string(video["snapshot_directory"], "video.snapshot_directory", allow_empty=True),
        ),
    )
