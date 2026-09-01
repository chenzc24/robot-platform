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


def load_runtime_config(path):
    """Load an explicit local JSON configuration without logging its contents."""
    source = Path(path)
    if not source.is_file():
        raise RuntimeConfigError("local configuration is unavailable")
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeConfigError("local configuration cannot be read") from error
    if set(raw) != {"schema_version", "chassis", "arm", "video"}:
        raise RuntimeConfigError("unexpected configuration fields")
    if raw["schema_version"] != 1:
        raise RuntimeConfigError("unsupported configuration schema")
    chassis = _mapping(raw["chassis"], "chassis")
    arm = _mapping(raw["arm"], "arm")
    video = _mapping(raw["video"], "video")
    if set(chassis) != {"host", "port", "client_id", "credential_env", "connect_timeout_seconds"}:
        raise RuntimeConfigError("unexpected chassis configuration fields")
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
