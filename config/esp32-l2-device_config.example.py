"""Non-secret device configuration for an ESP32 RCP/TCP v3 L2 release."""

RUN_MODE = "safe_idle"
RUNTIME_MODE = "tcp_v3_l2"
CONTROL_PORT = 8765
RUNTIME_BIND_ADDRESS = "0.0.0.0"
RUNTIME_HEALTH_TIMEOUT_MS = 2000
