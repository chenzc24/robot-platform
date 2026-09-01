# ESP32 COM7 read-only recognition

- Status:`completed`
- Responsible: Agent execution, user confirmation on site
- Highest validation level:`L2`

## Objective

Perform a read-only chip recognition of connected devices through COM7 to confirm whether they are targeted for ESP 32, do not erase, do not burn, do not modify the file system.

## Initial state of the workspace

```text
## main...origin/main
```

Workspace clean. Windows has identified COM7 as a normal WCH CH340 USB junction. `1A86:7523`; COM3 to COM6 are virtual bluetooth chains.

## Modifyable File

- `plan/2026-08-31-esp32-usb-inspection/plan.md`
- `plan/log.md`

## Read-only files and directories

- All remaining repository files
- ESP32 Device Flash and File System

## Shared Dependencies

- `.venv` verified `esptool 5.3.1`.
- VS Code develops a baseline to enter the target string as running time, without dying in the shared configuration.

## Risk and safety door

- Risk: Opening a serial may be re-engineered through DTR/RTS to re-enact ESP32, and re-run the existing program.
- Device: Target device on COM7.
- User Operations: The user has confirmed that the chassis is safe and can be identified in this cycle.
- Backup and recovery: This target does not write device and does not need to be restored; backup of the file system is a follow-up target.
- The campaign confirmed that the user has clearly confirmed the state of the site during this round.

## Expected work

1. Run `esptool --port COM7 chip-id`.
2. Document chip model, revised version and read-only recognition.
3. Do not continue the Flash writing or filesystem operation.

## Validation

- `.venv/Scripts/python.exe -m esptool --port COM7 chip-id`
- `git diff --check`
- `git status --short --branch`

## Actual results

- First implementation `esptool --port COM7 chip-id` Enables to open COM7, but ESP downloads handsshake without receiving any serial data, command to `Failed to connect to Espressif device: No serial data received` Over.
- Users manually enter download mode using BOOT/RST process for second recognition success.
- COM7 device is recognized as ESP32-S3 QFN56, Rev. v0.2, bi-nucleotide + low-powered nucleus, 240 MHz, 40 MHz crystal oscillation, 8MB embedded PSRAM, and support Wi-Fi and Bluetooth LE 5.
- `esptool`Read information after temporarily uploading the ID stub to RAM, unwieldy, burn or modify the device file system, and at the end pass the TRS hard reset device.

## Outstanding matters

- Not yet using MicroPython REPL to read the running version of the device or the backup file system.
- The Flash chip information has not yet been read; this reading can be added to the next L2 target with the backup of the file system.

## Experience signal (for manual review)


## Intent to submit

```text
docs: record ESP32 USB identification
```
