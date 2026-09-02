"""Create the ESP32 CAN adapter only in the explicitly selected L3 runtime."""


def _integer(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("%s must be an integer" % name)
    if value < low or value > high:
        raise ValueError("%s must be in %d..%d" % (name, low, high))
    return value


def create_can(config):
    """Construct one normal-mode ESP32 CAN bus from explicit local settings.

    This function has a hardware side effect and must be called only by the
    `tcp_v3_l3` composition after its physical safety gate. It sends no motor
    frame itself.
    """
    try:
        from esp32 import CAN
    except ImportError as error:
        raise RuntimeError("esp32_can_unavailable") from error

    bus_id = _integer(getattr(config, "CAN_BUS_ID", 0), "CAN_BUS_ID", 0, 1)
    baudrate = _integer(
        getattr(config, "CAN_BAUDRATE", 1000000),
        "CAN_BAUDRATE",
        10000,
        1000000,
    )
    tx = _integer(getattr(config, "CAN_TX_PIN", 8), "CAN_TX_PIN", 0, 48)
    rx = _integer(getattr(config, "CAN_RX_PIN", 18), "CAN_RX_PIN", 0, 48)
    if tx == rx:
        raise ValueError("CAN TX and RX pins must differ")

    can_bus = CAN(bus_id, mode=CAN.NORMAL, baudrate=baudrate, tx=tx, rx=rx)
    clear_rx_queue = getattr(can_bus, "clear_rx_queue", None)
    if callable(clear_rx_queue):
        clear_rx_queue()
    return can_bus
