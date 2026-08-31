"""Safe ESP32 application entry point.

Only modes whose complete safety path has been migrated may be added to
``SUPPORTED_RUN_MODES``. Missing, unknown, and partially migrated modes always
fall back to ``SAFE_IDLE`` without initializing motion hardware.
"""

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


def main():
    """Start in a mode whose hardware behavior is explicitly implemented."""
    requested_mode = load_requested_run_mode()
    run_mode = normalize_run_mode(requested_mode)
    if run_mode != requested_mode:
        print("unsupported run mode rejected; using SAFE_IDLE")
    print("robot-platform ESP32 mode:", run_mode)
    print("SAFE_IDLE: no motion hardware initialized")
    return run_mode


if __name__ == "__main__":
    main()
