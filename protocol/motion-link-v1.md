# RPA2 Arm Link v1

RPA2 uses `RPA2|TYPE|SEQUENCE|TTL_MS|PAYLOAD|CRC16\n` on MaixCam UART0, TCP232, and arm LAN1. Frames are ASCII, at most 512 bytes, use CRC-16/CCITT-FALSE, and reject malformed, duplicate, stale, oversized, or unknown input.

Queries use `PING → PONG` and `STATUS → STATE`. Accepted state-changing requests use `ACK → RUNNING → DONE`; an `ERROR` is terminal. `DONE` currently proves only that the controller API returned successfully. It does not prove physical terminal position: that capability is intentionally recorded as unavailable pending controller evidence.

MaixCam never retries a state-changing RPA2 frame. A write followed by timeout maps to `UNKNOWN` at the computer boundary.

The engineering project sets `YOLO_MODE=true` and accepts repeatable commands:

- `RELJOINT`: `joint_delta_deg` has six finite values and maps directly to
  `RelJointMovJ`.
- `RELLINEAR`: `translation_mm` has three finite X/Y/Z values and maps to
  `RelMovLUser` with zero rotational delta. Its integer `blend_pct` is 0 through
  100 and maps directly to the Dobot `cp` motion option. A controller upgraded
  first also accepts the legacy `blend_mm=0` form until MaixCam is upgraded.
- `MOVEJ`, `MOVEL`, and `GRIPPER` remain available to programmatic clients.

Acceleration and speed are integer percentages from 1 through 100. Relative
linear blending is the integer percentage described above; other primitive
blend fields remain zero. The application does not add a lease, one-use token, repeated enable,
or chassis-state gate in YOLO mode. Dobot controller limits, collision handling,
emergency stop, and recovery remain authoritative.
