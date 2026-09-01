# RCP1/TCP Chassis Link Version 1

## Scope

RCP1/TCP v1 proves the production application path from the computer to ESP32 over the trusted local Wi-Fi network. Version 1 is deliberately non-motion: only session establishment, liveness, and safe-state queries exist.

## Framing

- Transport: one TCP connection to the configured ESP32 runtime port; baseline `8765`.
- Encoding: ASCII JSON followed by one line-feed byte (`0x0A`).
- Maximum complete frame: 512 bytes including the terminator.
- Carriage returns, non-ASCII input, oversized frames, unknown fields, and unknown message types are rejected.
- TCP provides ordered integrity protection, so this transport does not add a CRC.

Every message contains exactly:

```json
{"version":1,"sequence":1,"type":"PING","ttl_ms":1000,"payload":{}}
```

| Field | Rule |
|---|---|
| `version` | Integer `1` |
| `sequence` | Integer `1..2147483647` |
| `type` | One v1 allowlisted uppercase type |
| `ttl_ms` | Request `100..5000`; response `0` |
| `payload` | Exact per-type object; no extra keys |

## Exchange

One client performs these operations in order without automatic retry:

```text
HELLO(client=console) → WELCOME(service=chassis, motion_enabled=false)
PING                  → PONG(protocol=1)
STATUS                → STATE(service=safe_idle, motion_enabled=false)
```

Responses reuse the request sequence. `ERROR` carries one lower-case identifier in `payload.code`. A TCP write, connect, or open port does not pass the link; all three matching responses are required.

## Safety Boundary

No acquire, heartbeat, enable, velocity, wheel, stop, disable, CAN, or motion message exists in v1. The ESP32 implementation must not import or initialize motion hardware. Runtime authentication, control leasing, heartbeat-driven local stop, and motion types require a later revision and separate L3 validation.
