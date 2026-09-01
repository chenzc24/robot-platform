# Deployment and Maintenance Baseline

- Status: individual development channels are available; atomic release, version rollback, and a unified release manifest are not complete
- Scope: publishing code from the computer to ESP32, MaixCam, and the robot arm; configuring TCP232; startup, health checks, and recovery
- Excludes: normal task commands and runtime behavior; see [Runtime Baseline](../runtime/README.md)

## 1. Deployment Topology

The maintenance plane allows the computer to reach each target independently:

```text
ESP32:   computer → Wi-Fi/WebREPL; USB for first configuration and recovery
MaixCam: computer → Wi-Fi/SSH/SCP; screen and USB virtual network for recovery
Robot arm: computer → wired LAN2 → DobotStudio Pro
TCP232:  computer → vendor configuration tool/page for one-time parameter checks
```

These maintenance paths are distinct from the runtime decision that ESP32 is the direct chassis endpoint and MaixCam is the arm/video endpoint. WebREPL and SSH must never become second runtime control owners.

## 2. Source of Truth

- Modify, test, and review production source in this repository before deploying it.
- A device filesystem is not the source of truth; recover every valid field change into Git-managed source.
- `ESP32/`, `Camera/`, and `Robot Arm_Claws/` are read-only raw-resource archives, not product releases.
- Store hotspot, SSH, WebREPL, and device credentials only in Git-ignored local configuration.
- Record the target version, device, file manifest, validation result, and recovery version for every release.

## 3. ESP32 Deployment

```text
VS Code local source
  ├── Wi-Fi/WebREPL: routine file upload and reset
  └── USB/mpremote/esptool: initial setup, backup, and recovery
```

- WebREPL is a deployment and maintenance channel, not the chassis runtime protocol.
- Entering the REPL can interrupt `main.py`. Close the session, reset the device, and restore the production service after deployment.
- The service starts in safe idle and never restores old velocity, enable state, or ownership.
- After reset, confirm version and state through the dedicated computer-ESP32 TCP handshake; do not interrupt the application by re-entering REPL merely to verify it.
- Only single-file WebREPL maintenance and protected reset currently exist. Release manifests, atomic switching, and automatic rollback remain unfinished.

Recovery order: confirm the current Wi-Fi address, attempt WebREPL maintenance, use USB for readback and single-file recovery, then restore known-good firmware. Never erase flash without a separate goal and confirmed backup.

## 4. MaixCam Deployment

```text
VS Code local source → SCP → /root/robot-platform/<release>
                              ↓
                         SSH start/stop,
                         status, and logs
```

MaixVision, MaixCode, and VS Code Remote-SSH are not deployment or runtime requirements. VS Code tasks are entry points for standard SSH/SCP commands.

Release requirements:

- Upload into a separate release directory; never treat temporary device edits as source.
- Record the active version and UART/camera owners before upload.
- Verify the intended owners of the camera, `/dev/ttyS0`, and `/dev/ttyS2` before startup.
- Restore prior launcher/service ownership if the gateway exits or fails to start.
- Pass local L1 and device-side non-motion L2 before enabling motion commands.
- Video and arm diagnostics currently use separate deployment directories; atomic publication and auto-start of the unified gateway are not implemented.

Recovery order: SSH, device screen, USB virtual network, then official image restoration.

## 5. Robot Arm Deployment

```text
VS Code-managed source
      ↓ reviewed copy/import
DobotStudio Pro
      ↓ LAN2
controller project, taught points, and configuration
```

LAN2 is used to import, save, start, and debug the project; configure taught points, load, safety settings, and controller mode; bind the controller Run/Stop button to a project; and inspect faults and actual state.

After the project is saved and started, LAN2 can be unplugged and runtime data continues through MaixCam-TCP232-LAN1. RPA1 has passed PING and one fixed action with LAN2 physically disconnected.

Do not infer automatic project start from cold boot. The current power-on sequence requires an on-site person to verify the initial pose, enable the arm, start the project using the configured controller button, and wait for MaixCam's non-motion handshake. Any future auto-start mode requires a separate vendor-supported safety-validation goal.

## 6. TCP232 One-Time Configuration

Current baseline:

```text
UART:    115200 8N1, no parity
Network: TCP Client
Target:  robot arm LAN1 192.168.5.1:5200
```

Read and verify the actual configuration before deployment. Do not change TCP232 addressing, mode, UART parameters, or target settings without explicit user authorization. Store exports or screenshots in a protected local resource location, not in Git.

TCP232 only transports bytes. The MaixCam gateway and robot-arm project must implement the same application protocol.

## 7. Recommended Release Order

For a cross-device protocol-version change, publish from execution endpoints toward the user-facing endpoint:

1. Stop automatic tasks and confirm chassis stop, arm safe pose, and release of old ownership.
2. Run local protocol vectors, simulators, and all relevant tests.
3. Deploy a compatible arm project through LAN2; leave it stopped or permit only non-motion handshake.
4. Deploy the compatible ESP32 version through WebREPL, reset to `safe_idle`, and close REPL.
5. Deploy the MaixCam arm/video gateway through SSH/SCP with arm motion input disabled.
6. Update the computer backend and console for both independent sessions.
7. Perform separate L2 version, state, and handshake checks for ESP32 TCP and the arm gateway.
8. Explicitly enable the runtime endpoint. Motion requires a separate L3/L4 safety gate.

Use rolling release only when the protocol explicitly supports both versions. Otherwise update all endpoints as one stopped-task release unit.

## 8. Release Health Check

Every endpoint reports at least:

```text
software_version
protocol_version
service_state
last_error
uptime
link_state
motion_enabled
```

The computer aggregates independently reported ESP32 and arm state into the system snapshot. Successful upload, a running process, or an open port alone is not release acceptance.

## 9. Rollback

- Keep the previous validated release directory and matching configuration template.
- For an incompatible protocol, stop from user-facing endpoint toward executors, then roll back from executors toward the endpoint.
- An ESP32 rollback must end in safe idle and repeat its handshake.
- A MaixCam rollback must restore UART and camera ownership.
- Roll back the arm through LAN2, restore the project and taught-point references, confirm Run-button configuration, then repeat non-motion PING.
- If an action result is unknown, inspect controller and physical state. Never resend the action merely to "verify" it.

## 10. Current Maturity

| Target | Available now | Still required |
|---|---|---|
| ESP32 | USB recovery, WebREPL single-file maintenance, protected reset | Release manifest, atomic upload, version query, rollback, production TCP service deployment |
| MaixCam | SSH/SCP, separate video and arm diagnostic directories, start/stop logs | Unified arm/video gateway release directory, auto-start, version switching, unified resource recovery |
| Robot arm | LAN2 project deployment, LAN1 diagnostic project, operation without LAN2 | Generic task project, version status, standard startup checks, rollback acceptance |
| TCP232 | Current parameters support RPA1 validation | Archived configuration export and automated read-only pre-release verification |

The next implementation goals are the ESP32 TCP chassis service/computer client and the MaixCam generic arm gateway. Do not begin with a three-device one-click deployment command that can trigger real hardware.
