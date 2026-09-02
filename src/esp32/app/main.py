"""Composition entry point for safe idle, L2, or the explicit guarded L3 listener."""

from application import (
    SAFE_IDLE,
    SUPPORTED_RUN_MODES,
    Esp32Application,
    load_requested_run_mode,
    normalize_run_mode,
)


def main():
    """Stay safe-idle unless local configuration explicitly selects L2 or L3."""
    application = Esp32Application()
    application.run()
    try:
        import device_config
        runtime_mode = getattr(device_config, "RUNTIME_MODE", "safe_idle")
    except ImportError:
        runtime_mode = "safe_idle"
    if runtime_mode not in ("tcp_v2_l2", "tcp_v2_l3"):
        return SAFE_IDLE
    from chassis_motion_tcp_server import ChassisMotionTcpServer
    from chassis_runtime_factory import make_l2_service, make_l3_service_factory
    port = getattr(device_config, "CONTROL_PORT", 8765)
    address = getattr(device_config, "RUNTIME_BIND_ADDRESS", "0.0.0.0")
    service_factory = (
        make_l2_service if runtime_mode == "tcp_v2_l2" else make_l3_service_factory()
    )
    ChassisMotionTcpServer(service_factory, port, address).run_forever()
    return runtime_mode


if __name__ == "__main__":
    main()
