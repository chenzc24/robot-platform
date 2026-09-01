# RCP/TCP Chassis Link Version 2

## Scope

RCP/TCP v2 is the motion-capable application contract between the computer console and the ESP32 chassis service. It does not replace or extend an active RCP1/TCP v1 session. A client must explicitly connect to a v2 service and receive `WELCOME(protocol=2)` before any control request.

The committed implementation is motion-disabled and uses injected dependencies only. This contract does not authorize deployment or real motion.

## Framing

- Transport: one persistent TCP connection on a locally configured runtime port.
- Encoding: canonical ASCII JSON followed by one line-feed byte (`0x0A`).
- Maximum frame: 512 bytes including the terminator.
- No carriage return, non-ASCII byte, unknown field, or unknown message type is accepted.
- TCP supplies ordered delivery and integrity; no application CRC is added.

Every message contains exactly:

```json
{"version":2,"sequence":7,"type":"PING","ttl_ms":1000,"payload":{}}
```

| Field | Rule |
|---|---|
| `version` | Integer `2` |
| `sequence` | Integer `1..2147483647`, strictly increasing per connection |
| `type` | One allowlisted uppercase type |
| `ttl_ms` | Request `100..5000`; response `0` |
| `payload` | Exact per-type object with no extra keys |

## Session and Ownership

```text
HELLO(client, credential) → WELCOME(protocol=2)
ACQUIRE(lease_ms)         → ACK → DONE
HEARTBEAT(lease_ms)       → ACK → DONE
RELEASE                   → ACK → DONE
```

The credential is checked by an injected local verifier. It is never echoed, logged, included in status, or committed to Git. The v2 baseline relies on the controlled WPA-protected LAN and does not claim TLS or internet-safe authentication.

Ownership belongs to the authenticated TCP session. Only the authenticated client may acquire or renew its lease. Lease expiry locally stops and disables the chassis and clears ownership.

## Commands

| Request | Payload | Local rule |
|---|---|---|
| `PING` | `{}` | Authenticated liveness query |
| `STATUS` | `{}` | Authenticated state query |
| `ACQUIRE` | `lease_ms: 250..2000` | Acquire the only control lease |
| `HEARTBEAT` | `lease_ms: 250..2000` | Renew the active lease |
| `ENABLE` | `{}` | Requires lease and local motion policy |
| `VELOCITY` | `vx_mm_s`, `vy_mm_s`, `omega_mrad_s`, `hold_ms` | Linear components `-600..600`, angular `-800..800`, hold `100..500`, and hold no longer than TTL |
| `STOP` | `{}` | Authenticated fail-safe zero request |
| `DISABLE` | `{}` | Authenticated zero plus motor-disable request |
| `RELEASE` | `{}` | Stop, disable, and clear ownership |

State-changing commands return either:

```text
ACK → DONE
ERROR
```

`DONE` means that the injected local chassis call returned without an exception. It does not prove measured wheel motion or physical stop because the current CAN path has no acknowledgement.

## Duplicate and Failure Rules

- An identical duplicate of the latest request replays cached responses and never re-executes motion.
- The same sequence with different bytes returns `sequence_conflict`.
- An older sequence returns `sequence_replay`.
- A malformed authenticated stream, TCP disconnect, lease expiry, velocity-hold expiry, short write, or execution exception invokes local stop and disable.
- A state-changing request with a lost response has an unknown outcome and is never automatically retried.
- Reconnection creates a new session, clears old sequence and ownership state, and requires a new `HELLO` plus `ACQUIRE`.

## Safety Boundary

The committed service has `motion_permitted=false`, a default-deny credential verifier, no socket listener binding, no CAN construction, and no startup integration. L2 must first prove a resident motion-disabled service. CAN integration and low-speed movement require a separate on-site L3 goal.
