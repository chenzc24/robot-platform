# Control Console L2 Connectivity Validation

- Status: `completed for the ESP32 L2 deployment; MaixCam validation deferred`
- Responsible: `agent`
- Highest validation level: `L2`

## Objective

Connect the computer console to the user-authorized ESP32, MaixCam arm endpoint, and MaixCam video stream on the current phone hotspot. Validate only connection, authenticated chassis `PING`/`STATUS`, arm `PING`/`STATUS`, video decode, explicit disconnect, and UI state/fault presentation. No motion or configuration write is admitted.

## Initial state of the workspace

The primary repository is on `target/computer-esp32-tcp-runtime` with one unrelated, user-owned `.vscode/settings.json` change. It remains untouched. This clean isolated worktree is `E:\Device Network - control-console-l2-connectivity`, branched from pushed L1 hardening commit `f69ccbb`.

## Modifiable files

- ignored `config/console.local.json` in this worktree, only if needed for this test
- `config/esp32-l2-device_config.example.py`
- `src/esp32/app/boot.py`, limited to invoking the already reviewed, no-motion
  application entry point after the isolated development-network bootstrap
- ESP32 filesystem only for the reviewed `tcp_v2_l2` release files after serial-port, power, backup, and recovery checks
- `plan/2026-09-02-console-l2-connectivity/plan.md`
- `plan/log.md`
- a narrowly scoped console L2 evidence document, if results require durable instructions

## Read-only files and directories

- all runtime source other than the declared ESP32 boot entry point, protocols,
  device source, configuration templates, VS Code settings, and raw-resource archives
- all existing local configuration, credential values, MaixCam services, ESP32 firmware, TCP232 settings, robot-arm project, CAN bus, motors, and taught points

## Shared dependencies

- Direct computer-to-ESP32 RCP/TCP v2 service, with motion disabled.
- MaixCam arm command service and RPA2/LAN1 path, with its default-deny arm policy.
- MaixCam RTSP stream and computer-side local relay, if already configured.
- Console L1 runtime adapter, strict status mapper, and Hardware-mode default-deny UI.

## User-authorized hardware state

- The user reports the computer, ESP32, MaixCam, and robot arm are powered, connected to the phone hotspot where applicable, and in a safe state.
- This goal is L2 only. The agent will not invoke lease, enable, heartbeat, velocity, stop, CAN, motor, RPA2 motion, or robot-arm motion functions.
- The user has additionally authorized USB deployment to the connected ESP32. The only permitted device write is the reviewed `tcp_v2_l2` no-motion release. Flash erase, firmware replacement, device configuration changes beyond selecting the documented L2 run mode, CAN construction, motor commands, and all mechanical motion remain prohibited.
- Deployment is paused before serial entry: the documented current root launcher is the historical PS2/CAN program, and a serial-tool reset can restart it before the no-motion replacement is established. This makes the transition a potential L3 safety exposure even though the destination release is L2-only.

## Risks and recovery

- Risk: a stale endpoint, missing credential, unstarted arm service, or unavailable RTSP route could cause connection or decode failure. Connection errors must not be inferred to be motion or hardware failure.
- Recovery: back up every overwritten device file first, retain USB access and the prior safe-idle launcher, then verify the deployed listener reports `motion_permitted=false` before ending the maintenance session. If deployment fails, restore the backed-up files over USB and reboot to safe idle.
- Secrets: host values and credential values stay in ignored local configuration/environment variables and are never committed or included in logs.

## Expected work

1. Inspect existing local, non-secret connection diagnostics to discover or confirm only the currently reachable endpoints.
2. Confirm the connected ESP32 serial port, MicroPython responsiveness, power state, filesystem capacity, current launcher/run mode, and recoverable backups before writing.
3. Upload only the reviewed `tcp_v2_l2` no-motion files and verify device-side hashes/readback. Start or select the L2 listener without constructing CAN.
   If the normal MicroPython launcher does not keep the reviewed listener alive,
   install the version-controlled boot entry point which invokes only `main.main()`;
   the selected L2 composition remains `NoMotionChassis` with motion disabled.
4. Prepare ignored console-local configuration without printing credentials.
5. Run the console runtime in Hardware mode and capture sanitized results for ESP32 connection, `PING`/`STATUS`, MaixCam arm connection, `PING`/`STATUS`, and video decoding.
6. Confirm the UI remains motion-locked, then explicitly disconnect all sessions.
7. Record only sanitized facts, validation results, and unresolved L2 blockers.

## Validation

- L1 regression suite and offscreen console smoke test before endpoint use.
- USB deployment preflight: exact port/model/revision, non-motion source review, device file backup, post-upload readback/hash, and recovery path confirmation.
- L2 runtime probe with allowed commands only: chassis connect/`PING`/`STATUS`; arm connect/`PING`/`STATUS`; video connect/decode; disconnect.
- Review captured command names and worker events to confirm no state-changing request names occur.
- `git diff --check` and repository status before commit.

## Actual results

- The computer is on the current hotspot subnet. MaixCam mDNS resolves and TCP port 22 is reachable. A non-interactive SSH attempt stopped at untrusted host-key verification; it did not authenticate, change the known-hosts file, or execute a remote command.
- MaixCam RTSP port 8554 and the current arm-service port 8780 are not listening. No process was started, stopped, or modified.
- A bounded read-only discovery sweep found no ESP32 RCP/TCP L2 port 8765 and no WebREPL port 8266 on the current hotspot subnet. Therefore the ESP32 endpoint address/service cannot yet be validated.
- No ignored console configuration was created because endpoint configuration and the chassis credential are unavailable. No application-level command, device write, motion, CAN frame, motor action, or robot-arm action was sent.
- USB preflight found COM7 among the attached serial devices, consistent with the documented ESP32-S3 mapping. The local Python environment currently lacks `mpremote` and `esptool`; no package was installed and no serial port was opened. Existing documentation confirms the device root currently starts a legacy PS2/CAN program after reset, so deployment cannot safely continue without the explicit transition safety confirmation below.
- After the user confirmed the transition safety gate, `mpremote` was installed
  locally and COM7 was used only for backup, deployment, readback, and reset.
  The existing root `boot.py`, `main.py`, `network_boot.py`, and `secrets.py`
  were copied into an ignored recoverable backup before replacement. No flash
  erase, firmware replacement, CAN action, motor action, or motion command was
  performed.
- Ten reviewed L2 runtime files were uploaded and read back with matching
  hashes. The device configuration selected `tcp_v2_l2`, and a local
  credential was generated in ignored configuration and installed on the
  device. The initial generated credential was too short for the v2 protocol;
  it was replaced with one that satisfies the protocol length and character
  rules before any authenticated request was sent.
- The normal MicroPython startup sequence did not keep the listener alive with
  the original boot hook. The declared, version-controlled `boot.py` was
  updated to invoke the already reviewed safe application entry point after
  network setup. Reset logs confirmed the application reached `safe_idle` and
  reported `motion_hardware_initialized=false`; the resident TCP port then
  accepted computer connections.
- Direct L2 evidence: a valid `HELLO`, `PING`, and `STATUS` session returned
  `WELCOME`, `PONG`, and `STATE` with sequences `1/2/3`. The state was
  `ready`/`disabled`, `motion_permitted=false`, authenticated, and without an
  active lease. A syntactically valid wrong credential was rejected with
  `authentication_failed`; a new valid session then connected and queried
  status successfully. All requests were read-only.
- The actual console runtime was configured through ignored local settings and
  completed `connect -> status -> disconnect` against the device. It did not
  submit a lease, enable, heartbeat, velocity, stop, disable, release, CAN,
  or motor request.

## Outstanding matters

- The user must start or confirm the existing MaixCam RTSP service and default-deny arm command service, then provide/verify their current endpoint settings. This goal does not authorize starting services or changing their configuration.
- L3 requires a new explicit on-site motion safety gate, reviewed limits, and a separate goal.

## Intent to submit

```text
docs: record console L2 connectivity evidence
```
