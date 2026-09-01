"""Composition entry point for safe idle or the explicitly non-motion v2 L2 listener."""

from application import (
    SAFE_IDLE,
    SUPPORTED_RUN_MODES,
    Esp32Application,
    load_requested_run_mode,
    normalize_run_mode,
)


def main():
    """Never create CAN/motors from the default application entry point."""
    application = Esp32Application()
    application.run()
    try:
        import device_config
        runtime_mode = getattr(device_config, "RUNTIME_MODE", "safe_idle")
    except ImportError:
        runtime_mode = "safe_idle"
    if runtime_mode != "tcp_v2_l2":
        return SAFE_IDLE
    from chassis_motion_tcp_server import ChassisMotionTcpServer
    from chassis_runtime_factory import make_l2_service
    port = getattr(device_config, "CONTROL_PORT", 8765)
    address = getattr(device_config, "RUNTIME_BIND_ADDRESS", "0.0.0.0")
    ChassisMotionTcpServer(make_l2_service, port, address).run_forever()
    return "tcp_v2_l2"


if __name__ == "__main__":
    main()
