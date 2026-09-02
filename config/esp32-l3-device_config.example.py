"""Non-secret configuration for the first guarded ESP32 chassis L3 release."""

RUN_MODE = "safe_idle"
RUNTIME_MODE = "tcp_v3_l3"
CONTROL_PORT = 8765
RUNTIME_BIND_ADDRESS = "0.0.0.0"
RUNTIME_HEALTH_TIMEOUT_MS = 2000

CAN_BUS_ID = 0
CAN_BAUDRATE = 1000000
CAN_TX_PIN = 8
CAN_RX_PIN = 18

# Keep false during deployment and CAN-safe-output validation. Set true only
# for the immediately approved, attended L3 wheel-rotation test.
L3_MOTION_PERMITTED = False
L3_MAX_LINEAR_SPEED_MM_S = 200
L3_MAX_OMEGA_MRAD_S = 400
L3_MAX_HOLD_MS = 500
