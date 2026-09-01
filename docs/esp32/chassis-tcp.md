# Computer-ESP32 Chassis TCP Link

- Protocols: [RCP1/TCP v1](../../protocol/chassis-tcp-v1.md) and [RCP/TCP v2](../../protocol/chassis-tcp-v2.md)
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

WebREPL can interrupt `main.py` and must never carry production velocity or heartbeat traffic. The runtime service is a separate socket owner, message parser, lifecycle, and safety state machine.

## 2. First Non-Motion Proof

The isolated ESP32 probe binds one TCP listener, accepts one client, and permits exactly:

```text
HELLO  → WELCOME
PING   → PONG
STATUS → STATE(service=safe_idle, motion_enabled=false)
```

It then closes. It does not import or initialize CAN, MotorBus, chassis motion, PS2, UART, or servo code. The computer client performs the three requests once and does not retry automatically.

The real-device proof returned matching sequences `1,2,3`, responses `WELCOME,PONG,STATE`, `service=safe_idle`, and `motion_enabled=false`. The ESP32 server reported one `console` client, three handled requests, and successful completion. This proves the isolated application transport only; it does not prove resident startup, authentication, heartbeat stopping, CAN integration, or motion.

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

- authenticated control acquisition and one active owner;
- heartbeat renewal and local stop/disable on expiry;
- bounded velocity, explicit stop, and disable types;
- safe CAN and MotorBus composition;
- state and fault feedback;
- restart, reconnect, stale-command, and duplicate-command behavior;
- resident startup and rollback.

That revision requires a fresh L3 goal. A successful non-motion TCP handshake does not authorize movement.

## 5. Local RCP/TCP v2 Foundation

RCP/TCP v2 is now implemented locally as a separate motion-capable revision. It does not modify v1 or convert the v1 hardware proof into motion evidence.

The v2 source consists of:

- `protocol/chassis_tcp_v2.py`: strict MicroPython-compatible JSON framing and validation;
- `src/esp32/app/chassis_motion_tcp_service.py`: injected authentication, ownership lease, heartbeat, bounded velocity, stop, disable, release, status, duplicate handling, and local watchdogs;
- `src/console/chassis_motion_tcp_client.py`: one-request-at-a-time client with lifecycle correlation and no automatic retry;
- `src/console/motion_router.py`: computer-side routing that sends chassis commands directly to ESP32 and arm commands only to the MaixCam arm session.

Committed safety defaults remain:

```text
credential verifier: absent, therefore authentication denied
motion_permitted: false
socket listener: not constructed
CAN and MotorBus: not constructed
startup integration: absent
```

An authenticated session must explicitly acquire a `250..2000 ms` lease and renew it with `HEARTBEAT`. Velocity contains a separate `100..500 ms` hold. Either deadline can stop and disable locally. Disconnect, malformed authenticated input, short write, or execution failure also attempts stop and disable before the session is closed.

The first credential is a local pre-shared value checked by an injected verifier. It is never included in committed configuration, responses, status, or logs. It is access control on the controlled WPA-protected LAN, not TLS and not a physical safety mechanism.

The next device step is not movement. A separate goal must bind a listener and deploy v2 with `motion_permitted=false`, then prove authentication rejection/acceptance, `PING`, `STATUS`, heartbeat expiry, disconnect cleanup, and rollback without CAN initialization. CAN composition and movement remain L3.
