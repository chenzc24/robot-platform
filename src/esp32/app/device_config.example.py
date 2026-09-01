"""Non-secret ESP32 device configuration template."""

RUN_MODE = "safe_idle"
DEVICE_NAME = "chassis-esp32"
CONTROL_PORT = 8765
HEARTBEAT_TIMEOUT_MS = 500

# First deployment candidate. `tcp_v2_l2` may serve only PING/STATUS/lease
# diagnostics because its composition uses NoMotionChassis. `safe_idle` remains
# the default. No CAN runtime mode is supplied until a separate L3 goal.
RUNTIME_MODE = "safe_idle"  # allowed: safe_idle, tcp_v2_l2
RUNTIME_BIND_ADDRESS = "0.0.0.0"

# Existing hardware assignments are documentation until verified on the board.
CAN_TX_PIN = 8
CAN_RX_PIN = 18
CAMERA_UART_TX_PIN = 5
CAMERA_UART_RX_PIN = 6
CAMERA_UART_BAUD = 115200
