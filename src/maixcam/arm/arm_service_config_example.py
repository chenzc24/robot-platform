"""Non-secret MaixCam arm endpoint template; copy to arm_service_config.py locally."""

LISTEN_ADDRESS = "0.0.0.0"
LISTEN_PORT = 8780
UART_DEVICE = "/dev/ttyS0"
UART_BAUD = 115200

# False remains the deploy-safe template. Set True in the ignored device-local
# configuration to expose repeatable manual/programmatic arm commands.
YOLO_MODE = False
