# Computer-to-MaixCam Control Envelope v1

Computer and MaixCam exchange one canonical ASCII JSON object per LF-terminated line. The maximum frame is 4096 bytes. This is the arm/video gateway protocol only; it never routes chassis traffic.

Each command has `version=1`, a strictly increasing `sequence`, unique `message_id`, `target`, `name`, `ttl_ms` in `100..60000`, and an exact object `payload`. MaixCam returns lifecycle records correlated through `correlation_id`:

```text
RECEIVED → ACCEPTED → RUNNING → DONE
                       └──────→ FAULT / UNKNOWN
RECEIVED → REJECTED
```

`UNKNOWN` means that an arm-affecting result cannot be established. It is never retried automatically. A TCP write, UART write, or TCP232 write is not `DONE`.

The command names are `arm.ping`, `arm.status`, `arm.jog_joint`, `arm.jog_xyz`,
`arm.move_joint`, `arm.move_linear`, `arm.gripper`, `arm.stroke_begin`,
`arm.stroke_append`, and `arm.stroke_execute`. The endpoint validates
exact payload fields, target/name consistency, one-in-flight transport ordering,
and remaining TTL before it creates an RPA2 request.

`arm.stroke_begin` and `arm.stroke_append` only stage a bounded controller-side
stroke; they do not move the arm. One append carries 1–8 relative draw segments
and one staged stroke holds at most 128. `arm.stroke_execute` is the only
motion-producing stroke request: it performs the staged anchor, pen-down,
continuous CP draw segments and pen-up as one controller-side transaction.
The client must stop on any non-`DONE` result and must not retry an uncertain
execution.

Site policy is not carried in commands. The committed templates remain
default-deny. A device-local `YOLO_MODE=true` deployment enables repeatable
manual/programmatic motion without an application lease, single-use grant, or
chassis interlock. The controller's native safeguards remain in force.
