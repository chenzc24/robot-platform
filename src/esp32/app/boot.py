"""MicroPython boot hook for the development network and safe application.

Network setup is isolated from the chassis application: a failed Wi-Fi or
WebREPL connection must not prevent ``main.py`` from starting. This hook does
not initialize any motion-related peripheral. The application entry point
selects its own fail-closed run mode; the L2 listener composes
``NoMotionChassis`` and therefore cannot initialize CAN or motors.
"""

from esp_runtime_status import RuntimeStatus


network_status = RuntimeStatus("esp32", "development_network")
network_status.transition("starting", event="network_starting")

try:
    from network_boot import start

    active_wlan = start()
    network_status.transition(
        "ready",
        event="network_ready",
        detail={
            "ipv4": active_wlan.ifconfig()[0],
            "webrepl_enabled": True,
        },
    )
except Exception as exc:
    network_status.transition(
        "fault",
        event="network_error",
        error_code="network_boot_failed",
        detail={"error_type": type(exc).__name__},
    )


try:
    from main import main as start_application

    start_application()
except Exception as exc:
    application_status = RuntimeStatus("esp32", "application_boot")
    application_status.transition(
        "fault",
        event="application_boot_error",
        error_code="application_boot_failed",
        detail={"error_type": type(exc).__name__},
    )
