"""Composition entry point for the safe ESP32 application runtime."""

from application import (
    SAFE_IDLE,
    SUPPORTED_RUN_MODES,
    Esp32Application,
    load_requested_run_mode,
    normalize_run_mode,
)


def main():
    """Start the local safe lifecycle without initializing motion hardware."""
    return Esp32Application().run()


if __name__ == "__main__":
    main()
