# Single-Gateway Runtime Baseline

- Status: architecture confirmed; the generic runtime protocol and three resident device services are not yet complete
- Scope: normal operation of the computer, MaixCam, ESP32-S3, TCP232, and Magician 6 robot arm
- Excludes: source deployment, firmware recovery, teaching, and device parameter configuration; see [Deployment and Maintenance](../deployment/README.md)

## 1. Runtime Topology

During normal operation, MaixCam is the only device node directly accessed by the computer:

```text
Computer backend
vision inference, state calculation, task orchestration, unified console
          │
          │ Wi-Fi: video, commands, status
          ▼
MaixCam unified gateway
    ├── UART2 /dev/ttyS2
    │       ↕
    │    ESP32 UART1
    │       ↓
    │   safety state machine → CAN → chassis
    │
    └── UART0 /dev/ttyS0
            ↕
          TCP232
            ↕ wired TCP
       robot arm LAN1 service
            ↓
       Dobot action execution
```

Only the computer and MaixCam must join the LAN at runtime. ESP32 does not depend on Wi-Fi, and robot arm LAN2 may be disconnected. ESP32, MaixCam, TCP232, and the robot arm must still be powered and running their local services.

## 2. Responsibility Boundaries

| Node | Runtime responsibilities | Explicit exclusions |
|---|---|---|
| Computer | Receive video, run vision inference, compute high-level state, orchestrate tasks, send tasks to MaixCam | Does not control CAN directly and is not the sole emergency-stop or interlock layer |
| MaixCam | Sole computer-facing device gateway, video output, command validation and routing, status aggregation, cross-device task gates | Does not transparently forward arbitrary motion parameters or replace local device safety |
| ESP32 | Receive UART commands, own chassis control, enforce TTL/heartbeat and speed limits, execute CAN commands, report status | Does not depend on the computer or Wi-Fi for safe stopping and does not control the arm |
| TCP232 | Transparent byte transport between MaixCam UART and robot arm LAN1 TCP | Does not parse the application protocol or decide whether an action completed |
| Robot arm | Host the LAN1 service, parse commands, own its action state machine, call the Dobot API, report results | Does not accept a second computer runtime owner and does not use LAN2 for runtime data |

## 3. Runtime Channels

| Channel | Direction | Transport | Current status |
|---|---|---|---|
| Video | MaixCam → computer | RTSP/H.264; FFmpeg/MediaMTX exposes local RTSP, HLS, and WebRTC | Passed continuous real-device video validation |
| Commands and aggregate status | Computer ↔ MaixCam | Persistent bidirectional application connection with framed structured messages | Not implemented |
| Chassis commands and status | MaixCam ↔ ESP32 | UART at a 115200 baseline, with framing, sequence, TTL, checksum, and heartbeat | Legacy receiver skeleton exists; formal protocol not implemented or validated |
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

Byte-oriented device links also require a length, frame terminator, and CRC. A receiver rejects unknown versions or targets, invalid or out-of-range values, duplicate/expired/out-of-order commands, commands without ownership, commands illegal in the current state, oversized frames, checksum failures, and incomplete frames.

Device command sets remain separate:

```text
chassis: acquire / heartbeat / velocity / stop / disable / status
arm:     ping / initialize / execute_named_action / cancel / status
system:  snapshot / fault / estop_state
```

MaixCam parses and validates each computer message, checks system state, and converts it to the ESP32 or robot-arm protocol. It must never pass arbitrary strings or unchecked trajectories directly to an actuator.

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

The resident gateway coordinates video and camera ownership, the computer command/status session, ESP32 UART, arm UART/TCP232, queues, sequence matching, timeouts, status aggregation, and local task gates between chassis stop and arm motion.

MaixPy's default communication listener may own `/dev/ttyS0`. The existing video backend removes that listener, but the final gateway must explicitly enforce single ownership of the camera, UART0, and UART2. Independent processes must not race for device nodes.

### 6.2 ESP32

The resident chassis service starts in safe idle, then initializes UART, its state machine, and CAN. It stops locally on UART loss, heartbeat expiry, or parse failure. Wi-Fi and WebREPL do not participate in runtime control.

The legacy program only prints MaixCam strings and returns raw `ok`; it does not safely map commands to chassis motion and cannot serve as the production runtime service.

### 6.3 Robot Arm

The controller runs a DobotStudio project that hosts a LAN1 TCP service and waits for TCP232 input. Once the project is running, LAN2 can be unplugged; non-motion PING and one fixed low-speed action have passed in that state.

Do not assume cold-boot auto-start. The current safe sequence is to verify the initial pose and workspace, enable the arm, start the configured project with the controller's run button, and require a non-motion readiness handshake from MaixCam before accepting an action.

## 7. Normal Startup

1. Restrain the chassis or place it in the agreed safe area, and place the arm at its safe initial pose.
2. Power ESP32, MaixCam, TCP232, and the robot arm.
3. ESP32 enters `safe_idle`, starts UART, and does not restore an old velocity.
4. An on-site person enables the arm and starts the configured LAN1 project.
5. MaixCam acquires UART ownership and performs non-motion handshakes with ESP32 and the arm.
6. MaixCam starts its computer command/status endpoint and video service.
7. The computer connects and obtains a complete status snapshot.
8. After every required component is `READY`, the computer explicitly acquires task control.

A missing state keeps the system idle. Link recovery never replays an old command automatically.

## 8. Fault Handling and Local Safety

| Fault | Required local behavior |
|---|---|
| Computer or Wi-Fi disconnects | MaixCam accepts no new tasks from that session; ESP32 stops under its UART heartbeat policy |
| MaixCam process exits | ESP32 stops after UART heartbeat timeout; the arm receives no new task; in-flight action status follows the real protocol evidence |
| MaixCam-ESP32 UART disconnects | ESP32 stops and retains/reports fault; MaixCam rejects chassis-dependent tasks |
| MaixCam-arm link disconnects | MaixCam enters `FAULT`; an uncertain non-idempotent action becomes `UNKNOWN` and is not retried |
| Video disconnects | Stop vision-dependent decisions; never continue from the last frame |
| A device restarts | Clear ownership, queues, and old sequence state, then repeat non-motion handshakes |

The physical emergency stop, robot limits, and ESP32 local stop must not depend on the computer, Wi-Fi, SSH, WebREPL, or a MaixCam software stop.

## 9. Implementation Order

1. Define the shared envelope, state semantics, cross-device vectors, and simulators.
2. Implement the ESP32 UART safety service and pass L1 plus non-motion L2.
3. Implement the MaixCam ESP32 adapter and computer command/status gateway.
4. Extend RPA1 diagnostics into a bounded generic arm task service without arbitrary trajectory pass-through.
5. Implement the computer-side MaixCam client, vision input, and task state machine.
6. Progress through L2 connectivity, L3 single-device motion, and L4 interlock validation.

Do not begin a higher-risk motion stage until failure, reconnect, and timeout behavior of the preceding layer has passed.
