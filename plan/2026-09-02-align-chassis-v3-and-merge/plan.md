# Align Chassis v3 Deployment Inputs and Merge

- Status: `complete (local alignment and Git integration; deployment pending)`
- Responsible: `agent`
- Highest validation level: `L1`; no device connection or deployment

## Objective

Complete the local RCP/TCP v3 alignment after removal of the chassis lease
layer, then integrate the reviewed target branch into `main` and push it.

## Initial workspace state

```text
## target/remove-chassis-lease...origin/target/remove-chassis-lease
 M .vscode/settings.json
```

The `.vscode/settings.json` modification is user-owned and remains untouched,
unstaged, and uncommitted. The ignored local console configuration is already
schema 2. The ignored ESP32 `device_config.py` still selects `tcp_v2_l3`.

## Editable scope

- ignored `src/esp32/app/device_config.py`, limited to runtime-mode and health
  timeout migration while retaining existing CAN pins, motion permission, and
  motion limits
- stale v2 wording in the active ESP32 service
- this goal plan and `plan/log.md`
- Git branch integration state

## Read-only scope

- `.vscode/settings.json`
- credentials and `src/esp32/app/secrets.py`
- `ESP32/`, `Camera/`, `Robot Arm_Claws/`, MaixCam, robot-arm, TCP232, CAN
  assignments, physical limits, and every real device filesystem

## Validation

- compare PC configuration and calls against ESP32 v3 protocol/service fields
- protocol, ESP32, console, development-tool, MaixCam, and robot-arm tests
- Python source validation, offscreen UI smoke, local config parsing,
  `git diff --check`, staged scope review, and branch synchronization

## Merge intent

Commit the tracked alignment record on `target/remove-chassis-lease`, merge it
into `main`, and push `main`. The ignored local device configuration is a
deployment input but cannot enter Git. Physical ESP32 deployment remains a
separate explicitly authorized L2/L3 action.

## Actual result

- The ignored local ESP32 deployment configuration now selects `tcp_v3_l3`
  and defines `RUNTIME_HEALTH_TIMEOUT_MS = 2000`.
- Existing local L3 motion permission, CAN assignments, and 200 mm/s,
  400 mrad/s, 500 ms motion limits were retained. They match the ignored PC
  console configuration; its 500 ms `PING` interval is within the ESP32 health
  deadline.
- Active source, templates, manifest, PC client/UI, and ESP32 runtime all use
  RCP/TCP v3. No active v2 import, mode, lease field, or lease API remains.
- The only remaining v2 deployment document is explicitly labeled as a
  historical record.

## Actual validation

- Protocol: 28 passed plus 6 subtests.
- ESP32: 54 passed plus 2 subtests.
- Console: 49 passed.
- Development tooling: 25 passed.
- MaixCam: 53 passed; unchanged by the direct chassis contract.
- Robot arm: 16 passed; unchanged by the direct chassis contract.
- Python source validation, offscreen UI smoke, local console configuration
  parsing, diff-format checks, and final branch synchronization passed.
- No hardware connection, device write, or physical motion was performed.
