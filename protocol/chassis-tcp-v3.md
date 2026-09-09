# RCP/TCP Chassis Link Version 3

## Scope

RCP/TCP v3 is the motion-capable application contract between the computer console and the ESP32 chassis service. It intentionally removes the v2 acquire/heartbeat/release lease layer. A client must connect to a v3 service and receive `WELCOME(protocol=3)` before any control request.

The implementation supports a no-CAN L2 composition and a separately enabled
CAN L3 composition. Changing the contract does not itself deploy either mode or
authorize a real-motion test.

## Framing

- Transport: one persistent TCP connection on a locally configured runtime port.
- Encoding: canonical ASCII JSON followed by one line-feed byte (`0x0A`).
- Maximum frame: 512 bytes including the terminator.
- No carriage return, non-ASCII byte, unknown field, or unknown message type is accepted.
- TCP supplies ordered delivery and integrity; no application CRC is added.

Every message contains exactly:

```json
{"version":3,"sequence":7,"type":"PING","ttl_ms":1000,"payload":{}}
```

| Field | Rule |
|---|---|
| `version` | Integer `3` |
| `sequence` | Integer `1..2147483647`, strictly increasing per connection |
| `type` | One allowlisted uppercase type |
| `ttl_ms` | Request `100..5000`; response `0` |
| `payload` | Exact per-type object with no extra keys |

## Session

```text
HELLO(client)             → WELCOME(protocol=3)
ENABLE                    → ACK → DONE
PING / STATUS             → PONG / STATE
LINE_FOLLOW_STATUS        → LINE_FOLLOW_STATE
LINE_FOLLOW_START / STOP  → ACK → DONE
STOP / DISABLE            → ACK → DONE
```

The successful trusted-LAN TCP handshake is the controller; there is no credential field or separate ownership lease. The baseline relies on the controlled WPA-protected LAN and does not claim TLS or internet-safe authentication.

Only one TCP client is processed at a time. Closing or replacing the connection ends the control session.

## Commands

| Request | Payload | Local rule |
|---|---|---|
| `PING` | `{}` | Session liveness query |
| `STATUS` | `{}` | Session state query |
| `ENABLE` | `{}` | Requires a completed handshake and local motion policy |
| `VELOCITY` | `vx_mm_s`, `vy_mm_s`, `omega_mrad_s`, `hold_ms` | Linear components `-600..600`, angular `-800..800`, hold `100..500`, and hold no longer than TTL |
| `LINE_FOLLOW_START` | `direction` (`-1` or `1`) | Requires an explicitly configured local follower and `enabled_stopped`; starts local sensor-rate decisions |
| `LINE_FOLLOW_STATUS` | `{}` | Returns local state, sanitized reason and direction; refreshes connection health |
| `LINE_FOLLOW_STOP` | `{}` | Stops the local follower without disabling the active chassis session |
| `STOP` | `{}` | Session fail-safe zero request |
| `DISABLE` | `{}` | Session zero plus motor-disable request |

State-changing commands return either:

```text
ACK → DONE
ERROR
```

`DONE` means that the injected local chassis call returned without an exception. It does not prove measured wheel motion or physical stop because the current CAN path has no acknowledgement.

The line-follow extension is optional and backward-compatible for direct-drive
clients. A service without enabled local GPIO/tuning configuration returns
`line_follow_unavailable`; ordinary `VELOCITY` remains unchanged. Direct
velocity is rejected while line following is active, and line-follow start is
rejected while a direct velocity hold is active. Mode fallback is a new,
explicit PC task decision, never an automatic ESP32 reaction.

## Duplicate and Failure Rules

- An identical duplicate of the latest request replays cached responses and never re-executes motion.
- The same sequence with different bytes returns `sequence_conflict`.
- An older sequence returns `sequence_replay`.
- A malformed session stream, TCP disconnect, health timeout, short write, or execution exception invokes local stop and disable and closes the session.
- Velocity-hold expiry sends a local stop but preserves the active, enabled session for the next manual jog.
- The runtime steps an active local line follower while polling socket safety.
  A scheduler exception invokes stop/disable and closes the session.
- A state-changing request with a lost response has an unknown outcome and is never automatically retried.
- Reconnection creates a new session, clears old sequence state, and requires a new `HELLO`. It does not require `ACQUIRE`.

## Safety Boundary

The trusted-LAN deployment has no credential mechanism; motion permission remains explicit. L2 uses `tcp_v3_l2` with no CAN construction. The separately gated L3 composition is `tcp_v3_l3`.
