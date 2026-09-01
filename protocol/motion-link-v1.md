# RPA2 Arm Link v1

RPA2 uses `RPA2|TYPE|SEQUENCE|TTL_MS|PAYLOAD|CRC16\n` on MaixCam UART0, TCP232, and arm LAN1. Frames are ASCII, at most 512 bytes, use CRC-16/CCITT-FALSE, and reject malformed, duplicate, stale, oversized, or unknown input.

Queries use `PING → PONG` and `STATUS → STATE`. Accepted state-changing requests use `ACK → RUNNING → DONE`; an `ERROR` is terminal. `DONE` currently proves only that the controller API returned successfully. It does not prove physical terminal position: that capability is intentionally recorded as unavailable pending controller evidence.

MaixCam never retries a state-changing RPA2 frame. A write followed by timeout maps to `UNKNOWN` at the computer boundary.
