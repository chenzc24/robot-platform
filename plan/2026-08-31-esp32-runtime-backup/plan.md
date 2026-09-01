# ESP32 MicroPython While Running

- Status:`completed`
- Responsible: Agent execution, user on site
- Highest validation level:`L2`

## Objective

When running through COM7 to a properly started MicroPython, read the version and the file tree and back up the existing file system to the local ignore directory without modifying the device.

## Initial state of the workspace

```text
## main...origin/main
```

The previous target has confirmed COM7 as ESP32-S3. Users have returned the device to normal start-up mode according to RST and request continuation;

## Modifyable File

- `.vscode/tasks.json`
- `docs/esp32/development.md`
- `plan/2026-08-31-esp32-runtime-backup/plan.md`
- `plan/log.md`
- `device-backups/`(local directory ignored, not submitted)

## Read-only files and directories

- All remaining repository files
- ESP32 Device File System and Flash

## Shared Dependencies

- ESP32-S3.
- `.venv` Medium `mpremote 1.29.0`.
- `.gitignore` Excluded `device-backups/`.

## Risk and safety door

- Risk:`mpremote`The action will stop the current program and execute a soft reset for MicroPython; a serial handshake may trigger a reset.
- Device: ESP32-S3. on COM7
- User Operations: Users have continued as required by RST, and the current round has been confirmed for safety on site.
- Backup and Recovery: This target read-only device and copy files to time stamp Local directory.
- Motion confirmation: no movement code is uploaded or executed; the device is in user-identified security.

## Expected work

1. Read MicroPython Achieved, Version, Platform and Single ID Summary.
2. Read Device File Tree, recognize existing `boot.py`, `main.py` and application modules
3. Create Timetamp Backup Directory and Copy Device File System.
4. Verifying local backup readable, recording results; not uploading or deleting device files.
5. Correcting what you found in the connection. `mpremote fs tree` The compatibility of parameters.

## Validation

- `mpremote connect COM7 exec <read-only-runtime-query>`
- `mpremote connect COM7 fs tree -vsh :`
- Check the number of local backup execution files, size and SHA-256 list.
- `git check-ignore device-backups`
- `git diff --check`
- `git status --short --branch`

## Actual results

- `mpremote`Successfully connect MicroPython 1.27.0 (2026-05-11) to build target `ESP32_GENERIC_S3-SPIRAM_OCT`The platform is ESP32.
- The file tree has been read successfully: the device root directory has 11 Python files.`SmartHybridChasisDemo/` The same 11 files.
- All 22 files, 125684 bytes, have been copied to a local ignore directory `device-backups/esp32/20260831-111429/`.
- The 11 pairs of the root directory and subdirectories calculate the same file by name SHA-256, all of which are consistent; backup files are accessible.
- Root Directory `boot.py` not initializing externalities; root directories `main.py` UART, CAN AND THE ELECTRONICS. `robot_config.py` Yes `RUN_MODE="ps2"`After startup into PS2 control cycle.
- The first file tree command used a cross-check. `-s` and `-h` Parameter failed, VS Code was amended to mpremote 1.29.0 `-vh` And verify the pass.
- This target is not uploaded, device files are deleted or modified, chassis movement is not performed.

## Outstanding matters

- The current program will re-initiate the CAN and the electrics when they are back in position, and will need to remain on site safe until the next reset.
- We have not yet set up a cell phone hotspot.`webrepl_setup`Wireless.
- Device Roots with `SmartHybridChasisDemo/` The duplicate file should be followed by a retention strategy in the code migration target, which does not delete the device file.

## Experience signal (for manual review)


## Intent to submit

```text
docs: record ESP32 MicroPython runtime backup
```
