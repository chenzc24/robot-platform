# Reset local runtime base and VS Code portal

- Status:`completed`
- Responsible: Agent is locally implemented, and the user will verify later Take it.
- Highest validation level:`L1`

## Objective

If you do not connect, deploy or drive any real device, organize the current ESP32 and MaixCam slots into an extended English source base: retain validated security cores, add module boundaries, structured state and error feedback, resource ownership and control lease protections, and expand secure VS Code checks, tests, status and log portals.

`src/esp32/legacy/` It's a byte history snapshot, and the Chinese and English hybrid content is kept as it is. Project design and operation documents can continue to use Chinese; add new running codes, notes, logs, status and error codes in English.

## Initial state of the workspace

```text
## main...origin/main
 M .vscode/settings.json
```

`.vscode/settings.json` is the existing MicroPython button modified by the user, which is a read-only path to this target. This goal is adopted. `.vscode/tasks.json` Expand the callable access, do not overwrite, save or submit the settings.

## Modifyable File

- `src/esp32/app/`
- `src/maixcam/app/`
- `src/maixcam/video/`
- `protocol/`
- `tests/esp32/`
- `tests/maixcam/`
- `tests/protocol/`
- `tools/dev/`
- `.vscode/tasks.json`
- `README.md`
- `docs/overall-plan.md`
- `docs/runtime-foundation.md`
- `docs/esp32/`, `docs/maixcam/` document directly related to local running borders
- `src/esp32/README.md`, `src/maixcam/README.md`
- `plan/2026-08-31-runtime-foundation-refactor/plan.md`
- `plan/log.md`
- Python cache directory ignored by Git

## Read-only files and directories

- `.vscode/settings.json`
- `src/esp32/legacy/`
- `ESP32/`, `Camera/`, `Robot Arm_Claws/`
- Local `secrets.py`, `device_config.py`And all the real evidence.
- MaixCam, ESP 32, TCP 232 and Mechanical Arm Device File System and Current Process

## Shared Dependencies

- ESP32 `SafeMecanumChassis` and `MotorBus` There are currently 22 regression tests.
- MaixCam RTSP verified 1280 x 720, 20 fps, 2 Mbps default parameters and UART0 default release rules.
- `protocol/runtime-status.schema.json` It's going to be a shared status contract for ESP 32, MaixCam and the successor console.
- No robot arm command protocol is established in this target, UART leads, TCP 232 parameters or chassis remote motion protocol.

## Risk and safety door

- Risk: Change in the shared status contract across ESP32 and MaixCam; change in local code structure but not verified by a genuine machine.
- Device: Not required; prohibition on uploading, reset, camera launch and Can access.
- User Operations: None in current cycle; additional L2/L3 target validation later.
- Backup and recovery: Git keeps the currently controlled version; no changes are made to the existing backup and deployment of device.
- Movement confirmed: Not applicable, current round does not run real motion code.

## Expected work

1. Defines light, MicroPython compatible running-time state and wrong contract.
2. Keep the ESP32 safe-state machine and the CAN frame in place, increase the application life cycle, state snapshot, transfer count and independent control of the original language of the lease.
3. Split MaixCam RTSP into CLI, inject video services, resource ownership and structured state, retain original parameters and stop script entry.
4. Add contract, security, state, resources and failure rollback tests.
5. Add non-motion VS Code local check, group test, connect status, log and media status portal.
6. Update modular boundary, status contract, non-deployment boundary and subsequent machine acceptance requirements.

## Validation

- Add new tests with existing Python modules, including failure injection and structured state contracts.
- Python static, PowerShell and VS Code JSON.
- New official source non-ASCII scan, exclude read-only `legacy/`local secret values and users `.vscode/settings.json`.
- Secret, according to the certificate, current DHCP address, cache and source scan.
- `git diff --check`
- `git status --short --branch`

L1 covers local contracts, modules, trouble protection and tool portals. MaixPy's actual resources, MicroPython imports, device deployment and behaviour are recorded as not being performed, and a different target is set when users are on board.

## Actual results

- Add a new version of the running-time status Schema, and achieve common compliance with the ESP32 and MaixCam sets; Events, devices, subsystems and error codes validate naming rules before sending them out.
- The ESP32 portal is broken down to an application life cycle, state output and control lease; the chassis status machine and MotorBus add visible snapshots and send count, and the default entrance still does not initiate motor hardware.
- MaixCam video portal is split to CLI, available for infusion services, MaixPy backend and resource ownership;
- VS Code forms 41 task portals, adds a single local precheck, three sets of tests, working area validation, real-time link checking, video status/ log/computer relay and development session combination tasks; for users `.vscode/settings.json` Keep it as it is.
- Add a running-time boundary document, and sync it with the overall, ESS32 and MaixCam documents. All current round official source codes, notes, events and error codes are in English, and Chinese is reserved for design and security documents.
- L1 has passed 52 tests: 4 sharing protocols, ESSP32 30 and MaixCam 18; 18 official Python-source files are compiled without caches and local secret and device cover files are not read; Bash syntax, PowerShell resolution, VS Code JSON, shared Schema and source language check passed.
- This round is not connected, upload, restart or drive any real device, and the current device deployment version remains unchanged.

## Outstanding matters

- The new module has not yet been imported, deployed and activated on MicroPython 1.27.0 or MaixCam;
- ESP32 `ControlLease` (a) Local parking/deactivating has not yet been connected to the chassis;
- MaixCam rotates by 90 degrees, visual recognition and final console still need follow-up.
- 4 Git ignored history `__pycache__` The directory is still on-line; the deletion operation was rejected by the current local execution strategy. They will not enter Git, and new local prechecks and tests are set to do not generate bytes caches.

## Experience signal (for manual review)

- Candidate signal: Python compiles caches that may retain deleted local configuration bytes, and can then consider consolidating "cleaning caches and prohibiting testing to generate caches" into manual maintenance rules. This target only records facts, does not create empirical documents.

## Intent to submit

```text
refactor: establish modular device runtime foundation
```
