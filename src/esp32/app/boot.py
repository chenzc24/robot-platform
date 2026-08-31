"""MicroPython boot hook for the development network.

Network setup is isolated from the chassis application: a failed Wi-Fi or
WebREPL connection must not prevent ``main.py`` from starting.  This hook does
not initialize any motion-related peripheral.
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
