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

# Optional advanced drawing relocation. Keep false until the four GPIO pins,
# electrical polarity, centered pattern, steering sign and tuning have been
# physically reviewed. The ignored device_config.py must define the remaining
# LINE_FOLLOW_* fields only when enabling this feature.
LINE_FOLLOW_ENABLED = False
# When enabled in device_config.py, define all of these with physically reviewed
# values (examples intentionally omitted for pins):
# LINE_FOLLOW_LEFT_PIN = ...
# LINE_FOLLOW_RIGHT_PIN = ...
# LINE_FOLLOW_STATION_LEFT_PIN = ...
# LINE_FOLLOW_STATION_RIGHT_PIN = ...
# LINE_FOLLOW_PIN_PULL = "up"  # none, up, or down
# LINE_FOLLOW_ACTIVE_LEVEL = 0
# LINE_FOLLOW_STEERING_SIGN = 1
# LINE_FOLLOW_CENTER_PATTERN = "both_active"
# LINE_FOLLOW_FORWARD_SPEED_M_S = 0.08
# LINE_FOLLOW_CORRECTION_SPEED_M_S = 0.05
# LINE_FOLLOW_CORRECTION_OMEGA_RAD_S = 0.15
# LINE_FOLLOW_STATION_CONFIRM_MS = 120
# LINE_FOLLOW_LINE_LOSS_TIMEOUT_MS = 150
# LINE_FOLLOW_MAX_STEP_GAP_MS = 100

# Existing hardware assignments are documentation until verified on the board.
CAN_TX_PIN = 8
CAN_RX_PIN = 18
CAMERA_UART_TX_PIN = 5
CAMERA_UART_RX_PIN = 6
CAMERA_UART_BAUD = 115200
