# Direct Chassis and Arm-Gateway Runtime Baseline

- Status: direct computer-to-ESP32 chassis boundary confirmed; non-motion TCP foundation in progress; motion service and generic arm service are not yet complete
- Scope: normal operation of the computer, MaixCam, ESP32-S3, TCP232, and Magician 6 robot arm
- Excludes: source deployment, firmware recovery, teaching, and device parameter configuration; see [Deployment and Maintenance](../deployment/README.md)

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
| ESP32 | Receive direct TCP chassis commands, own chassis control, enforce ownership/TTL/heartbeat and speed limits, execute CAN commands, report status | WebREPL is maintenance-only; safe stopping cannot depend on the computer remaining online; no arm control |
| TCP232 | Transparent byte transport between MaixCam UART and robot arm LAN1 TCP | Does not parse the application protocol or decide whether an action completed |
| Robot arm | Host the LAN1 service, parse commands, own its action state machine, call the Dobot API, report results | Does not accept a second computer runtime owner and does not use LAN2 for runtime data |

## 3. Runtime Channels

| Channel | Direction | Transport | Current status |
|---|---|---|---|
| Video | MaixCam → computer | RTSP/H.264; FFmpeg/MediaMTX exposes local RTSP, HLS, and WebRTC | Passed continuous real-device video validation |
| Chassis commands and status | Computer ↔ ESP32 | Dedicated persistent TCP service with bounded newline-delimited messages, sequence, TTL, ownership, and heartbeat | Bounded non-motion RCP1/TCP handshake passed on real hardware; resident motion service not implemented |
| Arm commands and status | Computer ↔ MaixCam | Persistent bidirectional application connection with framed structured messages | Generic endpoint not implemented |
| Arm commands and status | MaixCam ↔ TCP232 ↔ arm LAN1 | UART 115200 8N1, transparent TCP transport, and a robot-arm project | RPA1 diagnostics and one fixed action passed; generic task protocol not implemented |

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

Byte-oriented device links require framing and integrity checks appropriate to their transport. TCP chassis messages use bounded newline-delimited JSON and rely on TCP integrity; UART arm messages retain explicit checksum requirements. A receiver rejects unknown versions or targets, invalid or out-of-range values, duplicate/expired/out-of-order commands, commands without ownership, commands illegal in the current state, oversized frames, and incomplete frames.

Device command sets remain separate:

```text
chassis: acquire / heartbeat / velocity / stop / disable / status
arm:     ping / initialize / execute_named_action / cancel / status
system:  snapshot / fault / estop_state
```

ESP32 parses and validates direct chassis messages. MaixCam parses and validates robot-arm messages. Neither endpoint accepts arbitrary strings or unchecked actuator parameters. The computer combines their reported states for cross-device task gates but does not weaken either device's local checks.

## 5. Command Lifecycle

Every traceable command keeps one sequence number through this lifecycle:

```text
RECEIVED → ACCEPTED → RUNNING → DONE
                └────────────→ FAULT / REJECTED / UNKNOWN
```

- `RECEIVED`: a complete frame arrived.
- `ACCEPTED`: the target validated and committed to handling it.
- `RUNNING`: physical execution has started.
- `DONE`: the target device reported successful completion; writing bytes is not completion.
- `FAULT`: the target explicitly reported failure.
- `REJECTED`: the command was not executed because state, parameters, TTL, or ownership were invalid.
- `UNKNOWN`: a link failed and execution or completion cannot be determined. Never auto-retry a non-idempotent command in this state.

The computer advances a task only after receiving a matching terminal state. A connected TCP socket, a successful UART write, an online TCP232, or a legacy "running" response is not proof of completion.

## 6. Resident Services

### 6.1 MaixCam

The resident gateway coordinates video and camera ownership, the computer arm command/status session, arm UART/TCP232, queues, sequence matching, timeouts, and arm status. It no longer owns an ESP32 UART or chassis command route.

MaixPy's default communication listener may own `/dev/ttyS0`. The existing video backend removes that listener, but the final gateway must explicitly enforce single ownership of the camera and UART0. Independent processes must not race for device nodes.

### 6.2 ESP32

The resident chassis service starts in safe idle, opens its dedicated TCP runtime port, and initializes the state machine and CAN only in a separately validated motion mode. It stops locally on client disconnect, heartbeat expiry, command expiry, parse failure, or ownership loss. WebREPL does not participate in runtime control.

The legacy program's Wi-Fi/WebREPL bootstrap and PS2 loop do not expose a production TCP chassis service. WebREPL execution is not a substitute for the resident endpoint.

### 6.3 Robot Arm

The controller runs a DobotStudio project that hosts a LAN1 TCP service and waits for TCP232 input. Once the project is running, LAN2 can be unplugged; non-motion PING and one fixed low-speed action have passed in that state.

Do not assume cold-boot auto-start. The current safe sequence is to verify the initial pose and workspace, enable the arm, start the configured project with the controller's run button, and require a non-motion readiness handshake from MaixCam before accepting an action.

## 7. Normal Startup

1. Restrain the chassis or place it in the agreed safe area, and place the arm at its safe initial pose.
2. Power ESP32, MaixCam, TCP232, and the robot arm.
3. ESP32 enters `safe_idle`, starts its TCP endpoint, and does not restore an old velocity, owner, or client session.
4. An on-site person enables the arm and starts the configured LAN1 project.
5. MaixCam acquires arm UART ownership and performs a non-motion handshake with the arm.
6. MaixCam starts its arm command/status endpoint and video service.
7. The computer connects independently to ESP32 and MaixCam and obtains complete status snapshots.
8. After every required component is `READY`, the computer explicitly acquires task control.

A missing state keeps the system idle. Link recovery never replays an old command automatically.

## 8. Fault Handling and Local Safety

| Fault | Required local behavior |
|---|---|
| Computer or hotspot disconnects | ESP32 stops under its local TCP heartbeat policy; MaixCam accepts no new arm tasks from that session |
| ESP32 TCP client disconnects | ESP32 stops locally, clears ownership and old sequence state, and requires a fresh handshake |
| MaixCam process exits | The arm receives no new task; in-flight action status follows the real protocol evidence; ESP32 chassis safety remains independent |
| MaixCam-arm link disconnects | MaixCam enters `FAULT`; an uncertain non-idempotent action becomes `UNKNOWN` and is not retried |
| Video disconnects | Stop vision-dependent decisions; never continue from the last frame |
| A device restarts | Clear ownership, queues, and old sequence state, then repeat non-motion handshakes |

The physical emergency stop, robot limits, and ESP32 local stop must not depend on the computer, Wi-Fi, SSH, WebREPL, or a MaixCam software stop.

## 9. Implementation Order

1. Define the shared envelope, state semantics, cross-device vectors, and simulators.
2. Implement the ESP32 TCP safety service and computer client; pass L1 plus non-motion hardware validation.
3. Add authenticated ownership, heartbeat stop, and bounded motion commands under a separate L3 goal.
4. Extend RPA1 diagnostics into a bounded generic arm task service without arbitrary trajectory pass-through.
5. Implement the computer-side MaixCam arm client, vision input, and cross-device task state machine.
6. Progress through L2 connectivity, L3 single-device motion, and L4 interlock validation.

Do not begin a higher-risk motion stage until failure, reconnect, and timeout behavior of the preceding layer has passed.
