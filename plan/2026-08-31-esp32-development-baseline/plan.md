# Establishment of ESP32 MicroPython development baseline

- Status:`completed`
- Responsible: Agent Implementation, user responsible for follow-up access
- Highest validation level:`L1`

## Objective

Create without connecting or writing real machines `VS Code + Python/Pylance + MicroPython + mpremote + esptool + WebREPL` ESP32 local development baseline, without ESP-IDF.

## Initial state of the workspace

```text
## main...origin/main
```

Workspace clean. Python 3.12 and 3.13 has been detected; this target has been selected to return only to COM3 to COM6 Bluetooth virtual link with Python 3.12.

## Modifyable File

- `.gitignore`
- `.vscode/`
- `README.md`
- `docs/overall-plan.md`
- `requirements-dev.txt`
- `src/esp32/`
- `docs/esp32/`
- `plan/2026-08-31-esp32-development-baseline/plan.md`
- `plan/log.md`

## Read-only files and directories

- `AGENTS.md`
- `docs/network/`
- `ESP32/`
- `Camera/`
- `Robot Arm_Claws/`
- `tmp/`

## Shared Dependencies

- Freezed MicroPython Program: ESP32 business code does not migrate to C/C++, ESP-IDF SDK is not used or extended on a daily basis.
- `docs/network/README.md` Cellular hot spots, WebREPL and secure borders.
- Current Local Custom Solid `ESP32/MicroPython1.27.bin`This goal is read and not recorded.

## Risk and safety door

- Risk: local tool installation and VS Code configuration; no access to device, no exercise.
- Device: Not required.
- User Operations: Follow-up L2 target connects ESP32 USB and operates BOOT/RST.
- Backup and recovery: This target does not write the device; The device file system must be backed up and information on chips and solids must be recorded before future brushing.
- Movement confirmed: not applicable.

## Expected work

1. Establishment of Python 3.12 virtual environment and installation of official `mpremote`, `esptool`.
2. Install the official WebREPL client on this machine and record its source and version.
3. Create VS Code recommended extension, interpreter setup and secure USB/Wi-Fi task portal.
4. Create `src/esp32/` Minimum security applications, configuration protocols and development instructions.
5. Validation tools are enforceable, Python files are compiled, JSON configuration is valid and the directory is still ignored.

## Validation

- `git diff --check`
- `git status --short --branch`
- `.venv/Scripts/python.exe -m mpremote --version`
- `.venv/Scripts/python.exe -m esptool version`
- `.venv/Scripts/python.exe -m compileall src/esp32`
- Parsing `.vscode/*.json` And the tool chain locks the file.
- `git check-ignore` Review of information, secret configuration, virtual environment and directory of local tools.

This target is up to L1, and only local tools and the minimum security Python code are verified; unexecuted USB or Wi-Fi machine tests are not written in.

## Actual results

- Created Python 3.12 virtual environment, installed and validated `mpremote 1.29.0` and `esptool 5.3.1`; `pip check` No relying error.
- Active `.tools/webrepl` Install the official WebREPL client and submit it from a fixed source `1e09d9a1d90fe52aba11d1e659afbc95a50cf088`.
- VS Code recommended extensions, interpreter settings, and deviceless, USB read, USB file, USB REPL and WebREPL tasks; no custom transfer protocols were achieved.
- Created `src/esp32/app` Minimum safe application, no secret configuration template and development instructions, and fixed the official source path to `src/esp32/`.
- Three VS Code JSON files were analyzed and ESS32 Python source code and official WebREPL client checked through Python compiler.
- First Mirror Header for Local Solid `esptool image-info` Valid with ESP32-S3, 8 MB, DIO, 80 MHz, build information with ESP-IDF `v5.4.2-dirty`.
- `git check-ignore` Confirming virtual environments, local tools, three directories and ESP32 secret/local configurations are ignored.
- Not connected, read, write or drive real ESP32 devices.

## Outstanding matters

- Actual ESP32 USB port, plate and device file system content has not yet been confirmed.
- MicroPython version that has not been backed up or read on the device.
- The complete mirror layout and target burn address of the local solid still need to be confirmed in conjunction with the device and supply side description.
- Cellular hotspots, WebREPL password settings and wireless file transfer are left to the next L2.

## Experience signal (for manual review)


## Intent to submit

```text
build: establish ESP32 MicroPython development baseline
```
