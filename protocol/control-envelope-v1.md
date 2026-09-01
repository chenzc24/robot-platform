# Computer-to-MaixCam Control Envelope v1

Computer and MaixCam exchange one canonical ASCII JSON object per LF-terminated line. The maximum frame is 4096 bytes. This is the arm/video gateway protocol only; it never routes chassis traffic.

Each command has `version=1`, a strictly increasing `sequence`, unique `message_id`, `target`, `name`, `ttl_ms` in `100..60000`, and an exact object `payload`. MaixCam returns lifecycle records correlated through `correlation_id`:

```text
RECEIVED → ACCEPTED → RUNNING → DONE
                       └──────→ FAULT / UNKNOWN
RECEIVED → REJECTED
```

`UNKNOWN` means that an arm-affecting result cannot be established. It is never retried automatically. A TCP write, UART write, or TCP232 write is not `DONE`.

The initial command names are `arm.ping`, `arm.status`, `arm.move_joint`, `arm.move_linear`, and `arm.gripper`. The endpoint validates exact payload fields, conservative limits, target/name consistency, one-in-flight ownership, and remaining TTL before it creates an RPA2 request.

Site policy is not carried in commands. The arm controller retains `MOTION_ENABLED=false` until a local policy supplies reviewed joint bounds, Cartesian bounds, user/tool frames, load/tool data, and limits. Missing policy rejects motion.
