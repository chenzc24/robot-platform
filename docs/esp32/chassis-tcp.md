# Computer-ESP32 Chassis TCP Link

- Protocol: [RCP/TCP v3](../../protocol/chassis-tcp-v3.md)
- Runtime port baseline: `8765`, configured locally rather than scattered through application code

## 1. Channel Separation

```text
Deployment and maintenance:
computer → Wi-Fi/WebREPL port 8266 → ESP32 filesystem and REPL

Production runtime:
computer → Wi-Fi/TCP configured runtime port → ESP32 chassis service
```

WebREPL can interrupt `main.py` and must never carry production velocity or connection-health traffic. The runtime service is a separate socket owner, message parser, lifecycle, and safety state machine.

## 2. Current RCP/TCP v3 Runtime

RCP/TCP v3 is the current motion-capable revision. It is intentionally incompatible with v2 because the acquire/heartbeat/release lease layer has been removed.

The v3 source consists of:

- `protocol/chassis_tcp_v3.py`: strict MicroPython-compatible JSON framing and validation;
- `src/esp32/app/chassis_motion_tcp_service.py`: trusted-LAN session handling, connection health, bounded velocity, stop, disable, status, duplicate handling, and local watchdogs;
- `src/console/chassis_motion_tcp_client.py`: one-request-at-a-time client with lifecycle correlation and no automatic retry;
- `src/console/motion_router.py`: computer-side routing that sends chassis commands directly to ESP32 and arm commands only to the MaixCam arm session.

Committed safety defaults remain:

```text
trusted-LAN HELLO: accepted without a credential field
motion_permitted: false
socket listener: available in explicit `tcp_v3_l2` and `tcp_v3_l3` compositions
CAN and MotorBus: not constructed by `tcp_v3_l2`
startup integration: selected by local ignored `device_config.py`
```

After `HELLO` succeeds, the TCP connection itself is the control session and `ENABLE` may be sent directly. `STOP` zeros motion without disabling. `DISABLE` stops and disables but retains the active connection, so `ENABLE` may be sent again. Disconnecting ends the session. Background `PING` requests maintain connection health; timeout stops, disables, and closes the session. Velocity contains a separate `100..500 ms` hold whose expiry stops motion without disabling, so an attended operator can jog again immediately.

The configured command ceiling is 600 mm/s resultant planar speed and
800 mrad/s angular speed, matching the current protocol and chassis-model
ceilings. Combined commands remain subject to the 200 RPM wheel-speed cap.
The ESP32 local configuration and console local configuration must carry the same
limits before the wider range is used; a UI-only increase is not deployment.

RCP/TCP v3 uses the controlled LAN and a single TCP session without a credential field. Before replacing an older device runtime, deploy `tcp_v3_l2` with `motion_permitted=false`, then prove HELLO, `PING`, `STATUS`, health timeout, disconnect cleanup, and rollback without CAN initialization. Only after that L2 proof should `tcp_v3_l3` be deployed and validated under a fresh on-site motion gate.
