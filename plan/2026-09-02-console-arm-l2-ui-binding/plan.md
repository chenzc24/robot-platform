# Console Arm L2 UI Binding and Diagnostics

- Status: `in-progress`
- Responsible: `joint`
- Highest validation level: `L2`

## Objective

Repair the local hardware-mode console binding to the deployed MaixCam RPA2 arm endpoint and make the same L2 diagnostics available through the flat `robot` CLI. Verify endpoint reachability, arm status, and default-deny admission without moving the arm. The GUI remains a human-facing control surface, not the primary diagnostic transport.

## Initial workspace state

```text
## main...origin/main
```

The repository is clean at `12ba775`. The resident MaixCam arm gateway remains running on the controlled WLAN; LAN2 is physically disconnected.

## Editable scope

- ignored `config/console.local.json` local endpoint values only
- `plan/2026-09-02-console-arm-l2-ui-binding/plan.md`
- `plan/log.md`
- `src/console/ui/runtime.py` and directly related local tests if the observed UI binding exposes a defect
- `tools/robot_cli.py` and `tests/dev/test_robot_cli.py`
- `docs/development-session.md` for the public diagnostic commands
- `src/maixcam/arm/arm_motion_gateway.py`, `src/maixcam/arm/command_service.py`, and their focused tests if the L2 diagnostic exposes a stale-response recovery defect

## Read-only scope

- ESP32, TCP232, and robot-arm device configuration except normal L2 socket traffic
- MaixCam device configuration except the reviewed arm-service source deployment needed to correct the observed diagnostic defect
- arm policy, motion admission, taught points, network settings, credentials, raw resource archives, and user-owned primary-worktree files

## Dependencies and safety

- MaixCam endpoint: `maixcam-6c7d.local:8780`, default-deny motion admission.
- The normal console and CLI checks use `PING` and `STATUS` only. The CLI may include one named `reject-motion` proof that sends a syntactically valid request solely to verify its expected local `admission_rejected` response; it must not retry and must fail if the endpoint accepts the request.
- If a stale UART response is observed after a timed-out safe request, the MaixCam gateway must discard only lower, already-expired downstream sequences. It must not let that stale frame fault or block a newer request. A higher or malformed response remains a fault; a device deployment uses SSH/SCP only and sends no motion command.
- No L3 authorization is present. No movement, enable, gripper, controller setting, or TCP232 write is allowed.

## Validation

- L0: local configuration parses; diff and workspace status are checked.
- L1: focused CLI tests cover stable text/JSON output, one-shot PING/STATUS checks, and strict rejection handling.
- L2: run the CLI against the deployed endpoint: `check` (PING/STATUS), then the expected-rejection proof. No UI motion command is used.

## Actual results

- The ignored local configuration parses with the MaixCam endpoint. The UI started, entered Hardware mode, and recorded the requested arm connection, but then failed locally with `No module named 'maixcam_arm_client'`. The endpoint did not receive an arm request and no motion was sent. Root cause: the packaged UI runtime adds `protocol/` to `sys.path` but not its sibling `src/console/` client-module directory.
- The runtime import-path correction and its local regression test are present but not yet committed. CLI implementation and validation are pending.
- The first CLI runs revealed an intermittent arm-gateway defect: a delayed reply for a previously timed-out safe request can be treated as a sequence mismatch against a later request, leaving the gateway pending and causing `request_in_flight`. The device service source will be repaired and separately revalidated before any UI recheck.

## Intent to submit

```text
test(console): bind hardware UI to default-deny arm gateway
```
