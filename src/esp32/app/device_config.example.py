"""Non-secret ESP32 device configuration template."""

RUN_MODE = "safe_idle"
DEVICE_NAME = "chassis-esp32"
CONTROL_PORT = 8765
RUNTIME_HEALTH_TIMEOUT_MS = 2000

# `tcp_v3_l2` may serve only authenticated PING/STATUS diagnostics because its
# composition uses NoMotionChassis. `tcp_v3_l3` is present for a separately
# authorized CAN deployment. `safe_idle` remains the committed default.
RUNTIME_MODE = "safe_idle"  # allowed: safe_idle, tcp_v3_l2, tcp_v3_l3
RUNTIME_BIND_ADDRESS = "0.0.0.0"

# Existing hardware assignments are documentation until verified on the board.
CAN_TX_PIN = 8
CAN_RX_PIN = 18
CAMERA_UART_TX_PIN = 5
CAMERA_UART_RX_PIN = 6
CAMERA_UART_BAUD = 115200
