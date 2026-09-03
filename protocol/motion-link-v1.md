# RPA2 Arm Link v1

RPA2 uses `RPA2|TYPE|SEQUENCE|TTL_MS|PAYLOAD|CRC16\n` on MaixCam UART0, TCP232, and arm LAN1. Frames are ASCII, at most 512 bytes, use CRC-16/CCITT-FALSE, and reject malformed, duplicate, stale, oversized, or unknown input.

Queries use `PING → PONG` and `STATUS → STATE`. Accepted state-changing requests use `ACK → RUNNING → DONE`; an `ERROR` is terminal. `DONE` currently proves only that the controller API returned successfully. It does not prove physical terminal position: that capability is intentionally recorded as unavailable pending controller evidence.

MaixCam never retries a state-changing RPA2 frame. A write followed by timeout maps to `UNKNOWN` at the computer boundary.

The engineering project sets `YOLO_MODE=true` and accepts repeatable commands:

- `RELJOINT`: `joint_delta_deg` has six finite values and maps directly to
  `RelJointMovJ`.
- `RELLINEAR`: `translation_mm` has three finite X/Y/Z values and maps to
  `RelMovLUser` with zero rotational delta.
- `MOVEJ`, `MOVEL`, and `GRIPPER` remain available to programmatic clients.

Acceleration and speed are integer percentages from 1 through 100. Blending is
disabled. The application does not add a lease, one-use token, repeated enable,
or chassis-state gate in YOLO mode. Dobot controller limits, collision handling,
emergency stop, and recovery remain authoritative.

## Fault capability extension v1 (local implementation, coordinated deployment)

The marker and 512-byte limit stay unchanged. CAPS returns CAPSTATE with ordered
fields fault_version, xyz_preflight, controller_query, controller_clear,
service_recover (version 1 and binary flags). The current controller project
advertises the final three flags as zero: there is no verified alarm adapter.

FAULTS carries scope=service or scope=controller and returns FAULTSTATE. Service
scope returns the latest error record, including an explicit none/fault_id=0
when no error has occurred. Controller scope requires capability and returns
controller_state, stationary, queue_empty, emergency_stop, raw_hex,
raw_truncated, sample_time_ms. Unknown/unavailable state is ERROR, not clear.

CLEARERR and RECOVER both require exactly confirm=1 and are state-changing.
Their terminal success sequence is ACK then DONE; errors are terminal ERROR.
CLEARERR only clears alarms after fresh stationary/empty-queue/no-estop checks
and verifies again. Its DONE payload is controller state plus before_raw_hex,
before_truncated, before_sample_time_ms, clear_vendor_code. RECOVER verifies
the same conditions plus no alarms, then returns
recovery=service_ready;motion_resumed=0. Neither resumes or enables motion.

ERROR now carries these exact ordered fields:

```text
error_code;retryable;category;vendor_code;vendor_api;raw_hex;raw_truncated;sample_time_ms;fault_id
```

retryable is always 0. vendor_code is an actual signed 32-bit integer or unknown.
raw_hex contains at most 64 bytes of UTF-8 compact JSON/native exception text;
raw_truncated marks a prefix. Controller timestamps are not PC UTC. The receiver
must preserve the numeric code and source, not collapse everything to a token.
The new gateway accepts legacy error_code/retryable payloads; old gateways do
not accept extended errors. Upgrade matching endpoints while tasks are stopped.

Computer envelope names are arm.capabilities, arm.faults ({scope}),
arm.clear_errors and arm.recover_service (strict JSON {confirm:true}). Rich ERROR
data is forwarded in fault, downstream_payload and downstream_sequence along
with the terminal FAULT. State-changing write failures/timeouts remain UNKNOWN.
Query timeout is FAULT. No request is replayed automatically.

See [fault-management design](../docs/robot-arm/fault-management.md) for evidence
retention, current unsupported capabilities and the future adapter contract.
