# Console ESP32 Safe-Status Diagnosis

- Status: `completed`
- Responsible: `agent`
- Highest validation level: `L2` (real connection, no motion)

## Objective

Diagnose why the console Hardware chassis session faults during its automatic
post-authentication `STATUS` query, without sending any state-changing request.

## Initial workspace state

`target/control-console-manual-l3` is synchronized with its remote after the
manual-panel commit. Ignored `.env` and `config/console.local.json` hold local
credentials and endpoint configuration and are read only.

## Editable scope

- This goal plan and `plan/log.md` for factual results.
- Console source/tests only if the diagnosis establishes a bounded display or
  safe-query handling defect.

## Read-only scope

- ESP32 device files/configuration, local secret/configuration files, protocol
  contract, MaixCam, robot arm, raw resources, and user settings.

## Shared dependencies

- Direct computer-to-ESP32 RCP/TCP v2 runtime and the console's non-retrying
  session worker.

## Safety and validation

- Read the local endpoint and credential without printing their values.
- Open one TCP session and issue only `HELLO`, `PING`, and `STATUS`.
- Do not issue `ACQUIRE`, `HEARTBEAT`, `ENABLE`, `VELOCITY`, `STOP`,
  `DISABLE`, or `RELEASE`; do not write, reset, or deploy to the ESP32.
- Record only redacted response types, error codes, and non-secret state.

## Actual results

- The first direct safe diagnostic could open a TCP connection but timed out
  waiting for the `HELLO` response. A second staged diagnostic then timed out
  while opening the configured runtime TCP connection. Neither issued a
  state-changing command.
- ICMP to the configured ESP32 host and a separate WebREPL TCP probe both
  succeeded. The device remains reachable on the development LAN, but its
  resident RCP/TCP runtime listener is not accepting the configured connection.
- The console fault is therefore correctly blocking `ENABLE`: it has no valid
  authenticated `STATE` reply. The immediate blocker is device-side runtime
  availability, not a console credential or enablement-gate failure.
- After the operator reset the ESP32, the planned L2 recheck passed:
  `WELCOME`, `PONG`, and `STATE` returned in one fresh session. The service
  reported `ready`, chassis `disabled`, motion permission true,
  authentication true, and no active lease. No state-changing request was
  sent in the recheck.

## Outstanding matters

- The console can now reconnect for an attended manual-panel session. Any
  `ACQUIRE`/`ENABLE`/motion test remains a new L3 action requiring an immediate
  on-site safety confirmation.

## Commit intent

```text
fix: surface esp32 safe-query diagnostics in console
```
