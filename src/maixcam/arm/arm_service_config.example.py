"""Non-secret MaixCam arm endpoint template; copy to arm_service_config.py locally."""

LISTEN_ADDRESS = "0.0.0.0"
LISTEN_PORT = 8780
UART_DEVICE = "/dev/ttyS0"
UART_BAUD = 115200

# Intentionally false. The endpoint has no deployment-time permission to move.
MOTION_COMMANDS_PERMITTED = False
