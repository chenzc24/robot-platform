"""MicroPython boot hook for the development network.

Network setup is isolated from the chassis application: a failed Wi-Fi or
WebREPL connection must not prevent ``main.py`` from starting.  This hook does
not initialize any motion-related peripheral.
"""

try:
    from network_boot import start

    start()
except Exception as exc:
    print("network bootstrap failed:", type(exc).__name__, exc)
