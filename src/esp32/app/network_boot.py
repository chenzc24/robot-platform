"""Connect to the local development Wi-Fi and start WebREPL."""

import time

import network


CONNECT_ATTEMPTS = 80
CONNECT_POLL_MS = 250


def _load_config():
    from secrets import WEBREPL_PASSWORD, WIFI_PASSWORD, WIFI_SSID

    if not WIFI_SSID:
        raise ValueError("WIFI_SSID is empty")
    if not WIFI_PASSWORD:
        raise ValueError("WIFI_PASSWORD is empty")
    if not 4 <= len(WEBREPL_PASSWORD) <= 9:
        raise ValueError("WEBREPL_PASSWORD must contain 4 to 9 characters")
    return WIFI_SSID, WIFI_PASSWORD, WEBREPL_PASSWORD


def _connect(wifi_ssid, wifi_password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if not wlan.isconnected():
        wlan.connect(wifi_ssid, wifi_password)
        for _ in range(CONNECT_ATTEMPTS):
            if wlan.isconnected():
                break
            time.sleep_ms(CONNECT_POLL_MS)

    if not wlan.isconnected():
        raise OSError("Wi-Fi connection timed out; status=%s" % wlan.status())
    return wlan


def start():
    """Start the development network and return the active WLAN object."""
    wifi_ssid, wifi_password, webrepl_password = _load_config()
    wlan = _connect(wifi_ssid, wifi_password)

    import webrepl

    webrepl.start(password=webrepl_password)
    print("development network ready:", wlan.ifconfig()[0])
    return wlan
