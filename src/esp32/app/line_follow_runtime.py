"""Construct the optional local line follower from explicit device settings."""

from line_following import LineFollowConfig, LineFollower


_PIN_FIELDS = (
    "LINE_FOLLOW_LEFT_PIN",
    "LINE_FOLLOW_RIGHT_PIN",
    "LINE_FOLLOW_STATION_LEFT_PIN",
    "LINE_FOLLOW_STATION_RIGHT_PIN",
)


def _required(config, name):
    if not hasattr(config, name):
        raise RuntimeError("missing_%s" % name.lower())
    return getattr(config, name)


def _pin_numbers(config):
    pins = []
    for field in _PIN_FIELDS:
        value = _required(config, field)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 48:
            raise RuntimeError("invalid_%s" % field.lower())
        pins.append(value)
    if len(set(pins)) != len(pins):
        raise RuntimeError("line_follow_pins_must_be_unique")
    return pins


def _default_pin_factory(number, pull_name):
    from machine import Pin

    if pull_name == "none":
        return Pin(number, Pin.IN)
    attribute = "PULL_UP" if pull_name == "up" else "PULL_DOWN"
    if not hasattr(Pin, attribute):
        raise RuntimeError("line_follow_pull_unavailable")
    return Pin(number, Pin.IN, getattr(Pin, attribute))


def create_line_follower(config, chassis, clock_ms=None, pin_factory=None):
    """Return None while disabled; otherwise validate before constructing GPIO."""
    if getattr(config, "LINE_FOLLOW_ENABLED", False) is not True:
        return None
    pins = _pin_numbers(config)
    pull_name = _required(config, "LINE_FOLLOW_PIN_PULL")
    if pull_name not in ("none", "up", "down"):
        raise RuntimeError("invalid_line_follow_pin_pull")
    factory = pin_factory or _default_pin_factory
    inputs = [factory(number, pull_name) for number in pins]
    follower_config = LineFollowConfig(
        active_level=_required(config, "LINE_FOLLOW_ACTIVE_LEVEL"),
        steering_sign=_required(config, "LINE_FOLLOW_STEERING_SIGN"),
        center_pattern=_required(config, "LINE_FOLLOW_CENTER_PATTERN"),
        forward_speed_m_s=_required(config, "LINE_FOLLOW_FORWARD_SPEED_M_S"),
        correction_speed_m_s=_required(
            config, "LINE_FOLLOW_CORRECTION_SPEED_M_S"
        ),
        correction_omega_rad_s=_required(
            config, "LINE_FOLLOW_CORRECTION_OMEGA_RAD_S"
        ),
        station_confirm_ms=_required(config, "LINE_FOLLOW_STATION_CONFIRM_MS"),
        line_loss_timeout_ms=_required(
            config, "LINE_FOLLOW_LINE_LOSS_TIMEOUT_MS"
        ),
        max_step_gap_ms=_required(config, "LINE_FOLLOW_MAX_STEP_GAP_MS"),
    )

    def read_sensors():
        values = [pin.value() for pin in inputs]
        return {
            "line_left": values[0],
            "line_right": values[1],
            "station_left": values[2],
            "station_right": values[3],
        }

    return LineFollower(chassis, read_sensors, follower_config, clock_ms=clock_ms)
