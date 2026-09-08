"""Secret-free local configuration shared by console frontends."""

import json
from dataclasses import dataclass, field
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
    health_interval_ms: int
    velocity_hold_ms: int
    linear_limit_mm_s: int
    angular_limit_mrad_s: int


@dataclass(frozen=True)
class ArmConfig(EndpointConfig):
    session_id: str


@dataclass(frozen=True)
class VideoConfig:
    rtsp_url: str
    webrtc_url: str
    connect_timeout_seconds: float
    snapshot_directory: str

    @property
    def complete(self):
        return bool(self.rtsp_url and self.connect_timeout_seconds > 0)


@dataclass(frozen=True)
class VisionConfig:
    enabled: bool = False
    board_layout_path: str = ""
    camera_calibration_path: str = ""
    dictionary: str = "DICT_APRILTAG_36H11"
    detection_fps: float = 5.0
    min_tag_edge_px: float = 24.0
    max_reprojection_error_px: float = 5.0
    min_confidence: float = 0.55
    stale_after_ms: int = 1200
    log_path: str = ""

    @property
    def complete(self):
        return bool(
            self.enabled
            and self.board_layout_path
            and self.camera_calibration_path
            and self.dictionary == "DICT_APRILTAG_36H11"
        )


@dataclass(frozen=True)
class LocalizationConfig:
    enabled: bool = False
    rail_axis: str = "x"
    json_axis: str = "x"
    json_origin_rail_position_mm: float = 0.0
    json_mm_per_rail_mm: float = -1.0
    settle_time_ms: int = 2000
    sample_window_ms: int = 3000
    min_valid_samples: int = 8
    min_visible_tags: int = 2
    max_position_spread_mm: float = 2.0

    @property
    def complete(self):
        return self.enabled


@dataclass(frozen=True)
class RuntimeConfig:
    chassis: ChassisConfig
    manual_chassis: ManualChassisConfig
    arm: ArmConfig
    video: VideoConfig
    vision: VisionConfig = field(default_factory=VisionConfig)
    localization: LocalizationConfig = field(default_factory=LocalizationConfig)


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


def _bounded_number(value, field, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise RuntimeConfigError("%s must be a number in %s..%s" % (field, low, high))
    return float(value)


def _nonzero_bounded_number(value, field, low, high):
    parsed = _bounded_number(value, field, low, high)
    if parsed == 0:
        raise RuntimeConfigError("%s must be nonzero" % field)
    return parsed


def _choice(value, field, choices):
    parsed = _string(value, field)
    if parsed not in choices:
        raise RuntimeConfigError("%s must be one of %s" % (field, ", ".join(sorted(choices))))
    return parsed


def load_runtime_config(path):
    """Load an explicit local JSON configuration without logging its contents."""
    source = Path(path)
    if not source.is_file():
        raise RuntimeConfigError("local configuration is unavailable")
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeConfigError("local configuration cannot be read") from error
    schema_version = raw.get("schema_version")
    expected = {"schema_version", "chassis", "manual_chassis", "arm", "video"}
    if schema_version in {4, 5}:
        expected.add("vision")
    if schema_version == 5:
        expected.add("localization")
    if set(raw) != expected:
        raise RuntimeConfigError("unexpected configuration fields")
    if schema_version not in {3, 4, 5}:
        raise RuntimeConfigError("unsupported configuration schema")
    chassis = _mapping(raw["chassis"], "chassis")
    manual_chassis = _mapping(raw["manual_chassis"], "manual_chassis")
    arm = _mapping(raw["arm"], "arm")
    video = _mapping(raw["video"], "video")
    vision = _mapping(raw["vision"], "vision") if schema_version in {4, 5} else None
    localization = _mapping(raw["localization"], "localization") if schema_version == 5 else None
    if set(chassis) != {"host", "port", "client_id", "credential_env", "connect_timeout_seconds"}:
        raise RuntimeConfigError("unexpected chassis configuration fields")
    if set(manual_chassis) != {"enabled", "health_interval_ms", "velocity_hold_ms", "linear_limit_mm_s", "angular_limit_mrad_s"}:
        raise RuntimeConfigError("unexpected manual chassis configuration fields")
    if set(arm) != {"host", "port", "session_id", "connect_timeout_seconds"}:
        raise RuntimeConfigError("unexpected arm configuration fields")
    if set(video) != {"rtsp_url", "webrtc_url", "connect_timeout_seconds", "snapshot_directory"}:
        raise RuntimeConfigError("unexpected video configuration fields")
    if vision is not None and set(vision) != {
        "enabled", "board_layout_path", "camera_calibration_path", "dictionary",
        "detection_fps", "min_tag_edge_px", "max_reprojection_error_px",
        "min_confidence", "stale_after_ms", "log_path",
    }:
        raise RuntimeConfigError("unexpected vision configuration fields")
    if localization is not None and set(localization) != {
        "enabled", "rail_axis", "json_axis", "json_origin_rail_position_mm",
        "json_mm_per_rail_mm", "settle_time_ms", "sample_window_ms",
        "min_valid_samples", "min_visible_tags", "max_position_spread_mm",
    }:
        raise RuntimeConfigError("unexpected localization configuration fields")
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
            health_interval_ms=_positive_int(manual_chassis["health_interval_ms"], "manual_chassis.health_interval_ms", 100, 1_000),
            velocity_hold_ms=_positive_int(manual_chassis["velocity_hold_ms"], "manual_chassis.velocity_hold_ms", 100, 500),
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
            webrtc_url=_string(video["webrtc_url"], "video.webrtc_url", allow_empty=True),
            connect_timeout_seconds=_timeout(video["connect_timeout_seconds"], "video.connect_timeout_seconds"),
            snapshot_directory=_string(video["snapshot_directory"], "video.snapshot_directory", allow_empty=True),
        ),
        vision=VisionConfig() if vision is None else VisionConfig(
            enabled=_boolean(vision["enabled"], "vision.enabled"),
            board_layout_path=_string(vision["board_layout_path"], "vision.board_layout_path", allow_empty=True),
            camera_calibration_path=_string(
                vision["camera_calibration_path"], "vision.camera_calibration_path", allow_empty=True
            ),
            dictionary=_string(vision["dictionary"], "vision.dictionary"),
            detection_fps=_bounded_number(vision["detection_fps"], "vision.detection_fps", 0.2, 30.0),
            min_tag_edge_px=_bounded_number(vision["min_tag_edge_px"], "vision.min_tag_edge_px", 4.0, 1000.0),
            max_reprojection_error_px=_bounded_number(
                vision["max_reprojection_error_px"], "vision.max_reprojection_error_px", 0.1, 100.0
            ),
            min_confidence=_bounded_number(vision["min_confidence"], "vision.min_confidence", 0.0, 1.0),
            stale_after_ms=_positive_int(vision["stale_after_ms"], "vision.stale_after_ms", 100, 60_000),
            log_path=_string(vision["log_path"], "vision.log_path", allow_empty=True),
        ),
        localization=LocalizationConfig() if localization is None else LocalizationConfig(
            enabled=_boolean(localization["enabled"], "localization.enabled"),
            rail_axis=_choice(localization["rail_axis"], "localization.rail_axis", {"x", "y", "z"}),
            json_axis=_choice(localization["json_axis"], "localization.json_axis", {"x", "y"}),
            json_origin_rail_position_mm=_bounded_number(
                localization["json_origin_rail_position_mm"],
                "localization.json_origin_rail_position_mm", -1_000_000.0, 1_000_000.0,
            ),
            json_mm_per_rail_mm=_nonzero_bounded_number(
                localization["json_mm_per_rail_mm"],
                "localization.json_mm_per_rail_mm", -10.0, 10.0,
            ),
            settle_time_ms=_positive_int(localization["settle_time_ms"], "localization.settle_time_ms", 0, 60_000),
            sample_window_ms=_positive_int(localization["sample_window_ms"], "localization.sample_window_ms", 100, 60_000),
            min_valid_samples=_positive_int(localization["min_valid_samples"], "localization.min_valid_samples", 1, 100),
            min_visible_tags=_positive_int(localization["min_visible_tags"], "localization.min_visible_tags", 1, 100),
            max_position_spread_mm=_bounded_number(
                localization["max_position_spread_mm"], "localization.max_position_spread_mm", 0.001, 100.0
            ),
        ),
    )
