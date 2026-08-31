"""Non-secret ESP32 device configuration template."""

RUN_MODE = "safe_idle"
DEVICE_NAME = "chassis-esp32"
CONTROL_PORT = 8765
HEARTBEAT_TIMEOUT_MS = 500

# Existing hardware assignments are documentation until verified on the board.
CAN_TX_PIN = 8
CAN_RX_PIN = 18
CAMERA_UART_TX_PIN = 5
CAMERA_UART_RX_PIN = 6
CAMERA_UART_BAUD = 115200
