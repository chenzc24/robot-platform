# ESP32 Existing chassis source tube and static audit

- Status:`completed`
- Responsible: Agent Implementation
- Highest validation level:`L1`

## Objective

Copy the backuped ESP32 directories of 11 Python files as historical baselines managed by the version, confirm copy integrity, and initiate static audits, movement control, communications, abnormal handling and security risks. This target is not connected, write or drive real device, and does not integrate historical baselines directly into current deployable ones `app/`.

## Initial state of the workspace

```text
## main...origin/main
```

Workspace clean. Source file from read-only backup ignored by Git `device-backups/esp32/20260831-111429/`; this backup and device root directory is confirmed in the previous target.

## Modifyable File

- `.gitattributes`
- `src/esp32/legacy/chassis_2026_08_31/`
- `docs/esp32/legacy-chassis-audit.md`
- `docs/esp32/development.md`
- `src/esp32/README.md`
- `plan/2026-08-31-esp32-legacy-source-baseline/plan.md`
- `plan/log.md`

## Read-only files and directories

- `device-backups/esp32/20260831-111429/`
- `ESP32/`, `Camera/`, `Robot Arm_Claws/` and `tmp/`
- `src/esp32/app/`
- Device file system and COM7
- Remaining repository files

## Shared Dependencies

- Complete ESP32 backup and SHA-256 consistency conclusion
- Current `src/esp32/app/` Wi-Fi/WebREPL Safe Start Baseline.
- Device duties, security doors and L0-L4 validation rules.

## Risk and judgement

- History code contains real power, CAN, UART and PS2 control logic;
- `main.py` Initiating externals during import, static compilation will not execute these statements.
- The snapshot must remain byte, the audit opinion is written in a stand-alone file, and the historical code is not repaired in the same target.
- The historical documents are valid UTF-8, but the combination of the LF and CRLF ends and contains the original trail blank; The freezing snapshot path saves with Git binary content and exempts the blanks, and avoids rewriting the historical bytes when checking out or formatting. Other sources still use the repository default blanks.
- Backup may contain device-specific parameters, but may not contain hot spots, WebREPL or other secrets;

## Expected work

1. Copy the backup root directory of 11 Python files in their original version of the historical baseline directory.
2. List of documents comparing sources and targets, size and SHA-256.
3. Compile all files using CPython static, not import, not execute hardware codes.
4. Audit initiates side effects, movement defaults, parking/deactivation paths, threads, communications resolution, abnormality and repositioning behavior.
5. Record the facts, risk classification and subsequent re-constructing of the boundary, not uploading device or conducting exercise tests within this target.

## Validation

- The 11 source documents are consistent with the release snapshot by SHA-256.
- `python -m compileall` Still compiled.
- Check import maps, top-level hardware side effects and key security calls.
- Check that there's no secret in the Git difference, that the device backup directory or source path is wrongly incorporated.
- `git diff --check`
- `git status --short --branch`

## Actual results

- From read-only backup root directory machine copying of 11 Python files to `src/esp32/legacy/chassis_2026_08_31/`;not including identical content `SmartHybridChasisDemo/` Second copy.
- 11 files are valid UTF-8, but line end format is mixed; `.gitattributes -text` Keep the version fast byte.
- Source backup corresponds to snapshot file names, bytes and SHA-256 item by 11/11.
- 11 historical documents and current `src/esp32/app/` all compiled via CPython static; neither imported nor executed MicroPython hardware module.
- Audit confirmed two deployment blockages: unknown `RUN_MODE` Examples of auto-executing a whole set of movements; failure to write to a non-zero target and no mandatory zero before re-enactment.
- The audit also recorded risks such as import, i.e. initialization hardware, abnormal limitless re-entry of CAN, loss of connection, lack of driver feedback, rudder starter action/time API compatibility, Camera UART naked string and thread life cycle.
- Fake MotorBus check to confirm speed limit effective, while confirming initial recurrence `stop()` Do not send a bus stop order, and after failure `drive()` It still produces speed writing.
- Add independent audit files and clearly mark history snapshots as non-deployable; no changes `src/esp32/app/`.
- Secret scan and Git format check passed; current round is not connected, write or drive real devices.

## Outstanding matters

- None of the blockages in the historical snapshots have been repaired in this target; the next target has to be selectively migrated and cannot be copied to the deployment catalogue as a whole.
- Whether or not to keep non-zero targets during a malfunction requires access to the protocol and verification of L2/L3 upon completion of software protection.
- Current MicroPython `ticks_add` Compatibility, Can feedback capability and sensor failure semantics still need specific confirmation.

## Experience signal (for manual review)

- (b) Stop, disable and re-energize must be verified in a visible zero target and feedback loop.

## Intent to submit

```text
docs: import and audit ESP32 chassis source baseline
```
