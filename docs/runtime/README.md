# Direct Chassis and Arm-Gateway Runtime Baseline

- Status (2026-09-03): ESP32 v3 and MaixCam arm/video services published with bounded L2 evidence; measured arm feedback and one attended four-stroke drawing have passed; coordinated L4 and cold-start/recovery acceptance remain incomplete
- Scope: normal operation of the computer, MaixCam, ESP32-S3, TCP232, and Magician 6 robot arm
- Excludes: source deployment, firmware recovery, teaching, and device parameter configuration; see [Deployment and Maintenance](../deployment/README.md)

Evidence: [dated deployment and feedback](../deployment/2026-09-03-esp32-maixcam.md)
and [console behavior](../console/control-console-ui.md). A subsequent attended
four-stroke drawing validation is historical observation-time evidence, not the
current power or connection state.

## 1. Runtime Topology

During normal operation, the computer maintains separate bounded sessions with ESP32 for chassis control and MaixCam for video and robot-arm control:

```text
Computer backend
vision inference, state calculation, task orchestration, unified console
    ├── Wi-Fi/TCP ──→ ESP32 safety state machine ──→ CAN ──→ chassis
    │                     ↑ commands/status
    │
    └── Wi-Fi ──────→ MaixCam video and arm gateway
                           │ UART0 /dev/ttyS0
                           ▼
                         TCP232
                           │ wired TCP
                           ▼
                    robot arm LAN1 service
```

The computer, MaixCam, and ESP32 must join the LAN at runtime. Robot arm LAN2 may be disconnected. ESP32, MaixCam, TCP232, and the robot arm must still be powered and running their local services.

## 2. Responsibility Boundaries

| Node | Runtime responsibilities | Explicit exclusions |
|---|---|---|
| Computer | Receive video, run vision inference, orchestrate tasks, own one direct ESP32 chassis session and one MaixCam arm/video session | Does not control CAN or arm LAN1 directly and is not the sole emergency-stop or interlock layer |
| MaixCam | Video output, robot-arm command validation/routing, arm status, and arm task gates | Does not route chassis commands or replace local device safety |
| ESP32 | Receive direct trusted-LAN TCP chassis commands, own chassis control, enforce TTL/connection-health and speed limits, execute CAN commands, report status | WebREPL is maintenance-only; safe stopping cannot depend on the computer remaining online; no arm control |
| TCP232 | Transparent byte transport between MaixCam UART and robot arm LAN1 TCP | Does not parse the application protocol or decide whether an action completed |
| Robot arm | Host the LAN1 service, parse commands, own its action state machine, call the Dobot API, report results | Does not accept a second computer runtime owner and does not use LAN2 for runtime data |

## 3. Runtime Channels

| Channel | Direction | Transport | Current status |
|---|---|---|---|
| Video | MaixCam → computer | RTSP/H.264; FFmpeg/MediaMTX exposes local RTSP, HLS, and WebRTC | Passed continuous real-device video validation |
| Chassis commands and status | Computer ↔ ESP32 | RCP/TCP v3 persistent TCP service with bounded newline-delimited messages, sequence, TTL and health polling | v3 deployed; trusted-LAN non-motion readiness passed; the dated deployment did not test motion |
| Arm commands and status | Computer ↔ MaixCam | Persistent bidirectional NDJSON control envelope | Measured feedback and attended drawing passed; committed configuration template remains default-deny; deployed attended configuration uses YOLO |
| Arm commands and status | MaixCam ↔ TCP232 ↔ arm LAN1 | UART 115200 8N1, RPA2 CRC frames, and a robot-arm project | RPA2 feedback and sequential drawing passed; source defaults remain motion-disabled unless the reviewed YOLO project is generated |

Video and control are independent channels. A dropped video frame must not block a stop command, and a healthy command connection must not imply that vision output is valid.

## 4. Unified Envelope and Device-Specific Commands

"Unified commands" means a common message envelope and lifecycle, not one raw string interpreted by every device. The envelope includes at least:

```text
schema_version
sequence
source
target
message_type
timestamp_ms
ttl_ms
payload
```

Byte-oriented device links require framing and integrity checks appropriate to their transport. TCP chassis messages use bounded newline-delimited JSON and rely on TCP integrity; UART arm messages retain explicit checksum requirements. A receiver rejects unknown versions or targets, invalid or out-of-range values, duplicate/expired/out-of-order commands, commands illegal in the current state, oversized frames, and incomplete frames.

Current device commands remain separate (not arbitrary API pass-through):

```text
chassis: enable / velocity / stop / disable / ping / status
arm:     ping / status / move_joint / move_linear / jog_joint / jog_xyz / gripper
```

Arm network cancellation and controller alarm clearing are not available in
this baseline. The separate fault-foundation draft is not deployed by merging
the drawing lineage. Query/status capability does not imply a physical stop.

ESP32 parses and validates direct chassis messages. MaixCam parses and validates robot-arm messages. Neither endpoint accepts arbitrary strings or unchecked actuator parameters. The computer combines their reported states for cross-device task gates but does not weaken either device's local checks.

## 5. Command Lifecycle

Every traceable command keeps one sequence number through this lifecycle:

```text
RECEIVED → ACCEPTED → RUNNING → DONE
                └────────────→ FAULT / REJECTED / UNKNOWN
```

- `RECEIVED`: a complete frame arrived.
- `ACCEPTED`: the target validated and committed to handling it.
- `RUNNING`: the service reports execution in progress; this is not independent physical-motion feedback.
- `DONE`: the target reports completion. For the current arm project this means the sequential controller API returned, not verified terminal pose or pen pressure; writing bytes alone is not completion.
- `FAULT`: the target explicitly reported failure.
- `REJECTED`: the command was not executed because state, parameters or TTL were invalid.
- `UNKNOWN`: a link failed and execution or completion cannot be determined. Never auto-retry a non-idempotent command in this state.

The computer advances a task only after receiving a matching terminal state. A connected TCP socket, a successful UART write, an online TCP232, or a legacy "running" response is not proof of completion.

## 6. Resident Services

### 6.1 MaixCam

The resident gateway coordinates video and camera ownership, the computer arm command/status session, arm UART/TCP232, queues, sequence matching, timeouts, and arm status. It no longer owns an ESP32 UART or chassis command route.

MaixPy's default communication listener may own `/dev/ttyS0`. The existing video backend removes that listener, but the final gateway must explicitly enforce single ownership of the camera and UART0. Independent processes must not race for device nodes.

### 6.2 ESP32

The resident chassis service starts in safe idle, opens its dedicated TCP runtime port, and initializes the state machine and CAN only in a separately validated motion mode. The authenticated connection is the controller; there is no acquire/release layer. It stops and disables locally on client disconnect, connection-health timeout, parse failure, or execution failure. Velocity-hold expiry stops motion but leaves the session enabled. WebREPL does not participate in runtime control.

The legacy program's Wi-Fi/WebREPL bootstrap and PS2 loop do not expose a production TCP chassis service. WebREPL execution is not a substitute for the resident endpoint.

The v3 implementation separates four responsibilities:

```text
chassis_tcp_v3 codec
        ↓
ChassisMotionTcpService: trusted-LAN session, commands, lifecycle, watchdogs
        ↓ injected interfaces
SafeMecanumChassis
        ↓ configured CAN-backed runtime
MotorBus + MicroPython CAN
```

`ChassisMotionTcpRuntime` polls one injected connection and all local deadlines. `ChassisMotionTcpServer` binds one client. Ignored local configuration selects `tcp_v3_l2` for `NoMotionChassis` or the separately gated `tcp_v3_l3` CAN composition. The application entry remains safe idle until an explicit Enable request.

### 6.3 Robot Arm

The controller runs a DobotStudio project that hosts a LAN1 TCP service and waits for TCP232 input. Once the project is running, LAN2 can be unplugged; non-motion PING and one fixed low-speed action have passed in that state.

The later RPA2 project provides measured GetAngle/GetPose status and the
attended drawing primitives. Normalized feedback has passed live checks, but
raw vendor return containers and independent position accuracy were not
captured. Arm STATUS uses a 5000 ms query TTL in the shared PC client; it is
request-driven feedback, not concurrent in-motion telemetry.

Do not assume cold-boot auto-start. The current safe sequence is to verify the initial pose and workspace, enable the arm, start the configured project with the controller's run button, and require a non-motion readiness handshake from MaixCam before accepting an action.

## 7. Normal Startup

1. Restrain the chassis or place it in the agreed safe area, and place the arm at its safe initial pose.
2. Power ESP32, MaixCam, TCP232, and the robot arm.
3. ESP32 enters `safe_idle`, starts its TCP endpoint, and does not restore an old velocity or client session.
4. An on-site person enables the arm and starts the configured LAN1 project.
5. MaixCam acquires arm UART ownership and performs a non-motion handshake with the arm.
6. MaixCam starts its arm command/status endpoint and video service.
7. The computer connects independently to ESP32 and MaixCam and obtains complete status snapshots.
8. For a coordinated task, require current readiness and confirmed chassis stop before arm work. Attended YOLO/manual control remains independent as defined in the overall plan; there is no extra acquire/release API.

A missing state keeps the system idle. Link recovery never replays an old command automatically.

## 8. Fault Handling and Local Safety

| Fault | Required local behavior |
|---|---|
| Computer or hotspot disconnects | ESP32 stops and disables under its local TCP connection-health policy; MaixCam accepts no new arm tasks from that session |
| ESP32 TCP client disconnects | ESP32 stops locally, clears the active session and old sequence state, and requires a fresh handshake |
| MaixCam process exits | The arm receives no new task; in-flight action status follows the real protocol evidence; ESP32 chassis safety remains independent |
| MaixCam-arm link disconnects | MaixCam enters `FAULT`; an uncertain non-idempotent action becomes `UNKNOWN` and is not retried |
| Video disconnects | Stop vision-dependent decisions; never continue from the last frame |
| A device restarts | Clear sessions, queues, and old sequence state, then repeat non-motion handshakes |

The physical emergency stop, robot limits, and ESP32 local stop must not depend on the computer, Wi-Fi, SSH, WebREPL, or a MaixCam software stop.

## 9. Implementation Order

This is the original staged roadmap, not a claim that every item is still
unimplemented. Current publication and bounded acceptance are listed above;
remaining work includes cold-start/recovery validation, calibrated drawing,
vision-driven tasks and separately gated L4 coordination.

1. Define the shared envelope, state semantics, cross-device vectors, and simulators.
2. Implement the ESP32 TCP safety service and computer client; pass L1 plus non-motion hardware validation. RCP/TCP v3 is the current source contract; earlier versions provide historical hardware evidence only.
3. Bind and deploy v3 with motion disabled for L2 evidence, then deploy the reviewed CAN composition and bounded motion under a separate L3 gate.
4. Deploy the locally-tested RPA2 arm service and computer/MaixCam endpoint in their default-deny mode, without arbitrary trajectory pass-through.
5. Add authenticated arm-session admission, vision input, and cross-device task state only after their non-motion L2 evidence is complete.
6. Progress through L2 connectivity, L3 single-device motion, and L4 interlock validation.

Do not begin a higher-risk motion stage until failure, reconnect, and timeout behavior of the preceding layer has passed.
