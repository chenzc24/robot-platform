"""Non-secret MaixCam arm endpoint template; copy to arm_service_config.py locally."""

LISTEN_ADDRESS = "0.0.0.0"
LISTEN_PORT = 8780
UART_DEVICE = "/dev/ttyS0"
UART_BAUD = 115200

# Intentionally empty. A reviewed L3 deployment can allow only the named,
# one-use `arm.l3_j1_cycle` action; generic arm motion stays denied.
PERMITTED_MOTION_NAMES = ()
