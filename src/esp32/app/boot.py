"""Safe MicroPython boot hook.

The development baseline intentionally performs no network setup and initializes
no motion-related peripherals at boot. Wi-Fi bootstrap and device drivers will
be added only after the connected board and its existing filesystem are backed
up and verified.
"""
