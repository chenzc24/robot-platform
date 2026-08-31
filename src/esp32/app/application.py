"""Safe ESP32 application lifecycle without motion-side effects."""

from esp_runtime_status import RuntimeStatus


SAFE_IDLE = "safe_idle"
SUPPORTED_RUN_MODES = (SAFE_IDLE,)


def normalize_run_mode(requested_mode):
    """Return a supported mode, defaulting every invalid value to SAFE_IDLE."""
    if not isinstance(requested_mode, str):
        return SAFE_IDLE
    mode = requested_mode.strip().lower()
    if mode not in SUPPORTED_RUN_MODES:
        return SAFE_IDLE
    return mode


def load_requested_run_mode():
    """Read the local device override without making it mandatory."""
    try:
        import device_config
    except ImportError:
        return SAFE_IDLE
    return getattr(device_config, "RUN_MODE", SAFE_IDLE)


def _mode_for_detail(value):
    if value is None:
        return "none"
    if isinstance(value, str):
        return value
    return type(value).__name__


class Esp32Application:
    """Report a deterministic safe lifecycle while hardware modes are gated."""

    def __init__(self, requested_mode=None, status=None):
        self.requested_mode = (
            load_requested_run_mode() if requested_mode is None else requested_mode
        )
        self.status = status or RuntimeStatus("esp32", "application")

    def run(self):
        requested_mode = self.requested_mode
        run_mode = normalize_run_mode(requested_mode)
        self.status.transition(
            "starting",
            event="application_starting",
            detail={"requested_mode": _mode_for_detail(requested_mode)},
        )
        if run_mode != requested_mode:
            self.status.transition(
                "safe_idle",
                event="run_mode_rejected",
                error_code="unsupported_run_mode",
                detail={
                    "requested_mode": _mode_for_detail(requested_mode),
                    "active_mode": SAFE_IDLE,
                    "motion_hardware_initialized": False,
                },
            )
        else:
            self.status.transition(
                "safe_idle",
                event="application_ready",
                detail={
                    "active_mode": SAFE_IDLE,
                    "motion_hardware_initialized": False,
                },
            )
        return run_mode
