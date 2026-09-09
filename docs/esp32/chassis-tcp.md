# Computer-ESP32 Chassis TCP Link

- Protocols: historical [RCP1/TCP v1](../../protocol/chassis-tcp-v1.md) and current [RCP/TCP v3](../../protocol/chassis-tcp-v3.md)
- Runtime port baseline: `8765`, configured locally rather than scattered through application code
- Current safety boundary: session, liveness, and safe-state query only; no motion type exists
- Current validation: local L1 and one bounded real-device non-motion exchange passed on 2026-09-01

## 1. Channel Separation

```text
Deployment and maintenance:
computer → Wi-Fi/WebREPL port 8266 → ESP32 filesystem and REPL

Production runtime:
computer → Wi-Fi/TCP configured runtime port → ESP32 chassis service
```

WebREPL can interrupt `main.py` and must never carry production velocity or connection-health traffic. The runtime service is a separate socket owner, message parser, lifecycle, and safety state machine.

## 2. First Non-Motion Proof

The isolated ESP32 probe binds one TCP listener, accepts one client, and permits exactly:

```text
HELLO  → WELCOME
PING   → PONG
STATUS → STATE(service=safe_idle, motion_enabled=false)
```

It then closes. It does not import or initialize CAN, MotorBus, chassis motion, PS2, UART, or servo code. The computer client performs the three requests once and does not retry automatically.

The real-device proof returned matching sequences `1,2,3`, responses `WELCOME,PONG,STATE`, `service=safe_idle`, and `motion_enabled=false`. The ESP32 server reported one `console` client, three handled requests, and successful completion. This proves the isolated application transport only; it does not prove resident startup, connection-health stopping, CAN integration, or motion.

Implemented files:

- `protocol/chassis_tcp.py`
- `src/esp32/app/chassis_tcp_service.py`
- `src/esp32/app/chassis_tcp_probe.py`
- `src/console/chassis_tcp_client.py`
- `src/console/chassis_tcp_probe.py`

## 3. Hardware Validation Procedure

Because the deployed legacy application initializes CAN and motors after reset, WebREPL entry and restoration are treated as L3 even though the TCP probe itself is non-motion.

After the current safety gate is confirmed:

1. Confirm the ESP32 identity, power, current DHCP address, and WebREPL accessibility.
2. Interrupt the legacy application and issue its existing chassis-disable protection.
3. Inspect and back up any same-name target files.
4. Upload only the protocol, service, and bounded probe; do not replace `main.py`, `boot.py`, configuration, or legacy files.
5. Start the bounded ESP32 TCP probe through the protected REPL session.
6. Run the computer client once against the runtime port.
7. Require matching sequences `1,2,3`, responses `WELCOME,PONG,STATE`, and `motion_enabled=false`.
8. Close both sockets and restore the known device state under on-site supervision.

## 4. Required Motion Revision

The later production service must add, test, and validate together:

- trusted-LAN single-client session;
- connection-health polling and local stop/disable on timeout;
- bounded velocity, explicit stop, and disable types;
- safe CAN and MotorBus composition;
- state and fault feedback;
- restart, reconnect, stale-command, and duplicate-command behavior;
- resident startup and rollback.

That revision requires a fresh L3 goal. A successful non-motion TCP handshake does not authorize movement.

## 5. Current RCP/TCP v3 Runtime

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
