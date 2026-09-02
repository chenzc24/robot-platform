# ESP32 MicroPython Development Environment

- Status: USB restore channel, mobile phone hotspot automatic access and WebREPL completed L2 validation
- Run by: MicroPython
- IDE: VS Code + Python + Pylance
- Not required: ESP-IDF SDK, ESP-IDF VS Code Extension, C/C++ Migration

## Instrument boundaries

| Tools | Role | Whether to write devices |
|---|---|---|
| VS Code / Pylance | Edit and check Python source code | Yes |
| `mpremote` | USB enumerator, file, REPL, run and softback | Depending on the specific order. |
| `esptool` | Chip Information, Firmware Check, Firmware Burning | reading commands not written; burn commands Write |
| `webrepl.html` | Official WebREPL terminal and single file transfer on Windows | Write device file system during upload |
| MicroPython | Firmware and Python on ESP32 | Run on Device |

ESP-IDF is at the bottom of MicroPython firmware. ESP-IDF is only installed when a self-defined MicroPython firmware or C/C++ original module is added; daily Python development does not require it.

## 2. Local environment

Project fixes Python 3.12 virtual environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Directly dependent:

```text
mpremote 1.29.0
esptool 5.3.1
```

At the time the baseline was established, COM3 to COM6 were both a bluetooth virtual link; the first real machine connection added target device COM7.

The target device is identified as the WCH CH340 crossing on COM7 after the first real-time connection. MicroPython running time information:

```text
MicroPython 1.27.0 (2026-05-11)
Board: ESP32_GENERIC_S3-SPIRAM_OCT
Runtime: MicroPython / GIL
```

The device file system has read only backups to ignore directories `device-backups/esp32/20260831-111429/`22 files totalling 125684 bytes. `SmartHybridChasisDemo/` Each has the same set of 11 program files, one by one SHA-256. `robot_config.py` Current `RUN_MODE="ps2"`; root directories `main.py` The initialization of the CAN and the electrics and their entry into the PS2 control cycle, so any subsequent reset must remain chassis secure.

The development network has been validated through 2.4 GHz mobile hotspots. ESP32 can automatically access the DHCP address and activate WebREPL after restart; this round address is `10.114.1.97`, the address is not a fixed configuration, the hotspot should be redistributed using a list of mobile clients or a serial entry `WLAN.ifconfig()` Yes. ICMP and TCP 8266 between the computer and ESP32 have been validated.

WebREPL client from the official repository:

```text
https://github.com/micropython/webrepl.git
commit 1e09d9a1d90fe52aba11d1e659afbc95a50cf088
```

The new computer can be installed in a local ignore directory:

```powershell
git clone https://github.com/micropython/webrepl.git .tools\webrepl
git -C .tools\webrepl checkout 1e09d9a1d90fe52aba11d1e659afbc95a50cf088
```

`.venv/` and `.tools/` Not into Git.

## 3. VS Code mission

Pass. `Terminal → Run Task` Use task.

### Unequipped Tasks

- `ESP32: Check Python sources`
- `ESP32: Run safety tests`
- `ESP32: Tool versions`
- `ESP32: Inspect local firmware image`

### USB Read Job

- `ESP32: List USB devices`
- `ESP32: Read chip info (USB, no write)`
- `ESP32: USB file tree`Use `mpremote fs tree -vh`)
- `ESP32: USB download one file`

### USB write or run jobs

- `ESP32: USB upload one file`
- `ESP32: USB soft reset`
- `ESP32: USB REPL`

### Wi-Fi Task

- `ESP32: Open WebREPL browser client`

The task opens a fixed version of the official `webrepl.html`. Enter the current device address on the page, for example `ws://10.114.1.97:8266/`, manually enter the WebREPL password. The page provides both interactive terminals and single file uploads; it allows only one active connection, which should be closed before uploading.

Fixed version `webrepl_cli.py` Dependence on Unix in Windows Interactive Mode `termios`, and will rediscover the password entered in the status line, so it will not be exposed as a VS Code mission. Scripts will remain in the official tool catalogue of this machine, and will be used for routine command line deployment only after repairing or adding undisclosed thin packages upstream.

## 4. Why isn't there a "one-key fixer" mission?

This baseline deliberately does not provide a VS Code mission to erase and write to Flash. Before the first connection to the real device, the following information has not been confirmed:

- Actual ESP32-S3 plate, Flash capacity and serial.
- Current device file system content and recoverable backup.
- `MicroPython1.27.bin` The exact mirror type and burn address.
- How BOOT/RST enters download mode.

Upon completion of backup and read-only recognition, add one parameter based on the verification, clear, manual confirmation of the burn job. `erase-flash` As a general development shortcut.

Used `esptool image-info` Local `ESP32/MicroPython1.27.bin` Conduct a read-only check: First mirror identified as ESP32-S3, 8 MB Flash, DIO, 80 MHz, valid check and Hashi, build information as ESP-IDF `v5.4.2-dirty`...the result cannot yet independently prove the target burn address of the complete combined mirror, and therefore does not create the Flash job.

## 5. First real-time access completed

1. COM7 has been identified as target ESP32-S3, USB chip information and MicroPython was read while running.
2. Original device file system completed read-only backup, local firmware images were only formatted and did not brush or erase Flash.
3. `network_boot.py`It's ignored. `secrets.py` And new `boot.py` It's uploaded in recoverable order.
4. ESP32 automatically connects hotspots, restores WebREPL, logs in through local area networks and reads only the REPL probe.
5. Once validation has been completed, reset the device into the original PS2 start-up process; Reset the network guide and the WebREPL port is normal. This round does not send a motion command, nor does it replace or enter the device `main.py` And then run a check.

The above is L2 device connection. WebREPL may interrupt running when entering interactive REPL `main.py`Once debugging has been completed, repositioning must be confirmed. Any program that could trigger a chassis action must enter the L3 target separately and implement manual motion security doors.

## Source code and secret configuration

```text
src/esp32/
├── README.md
└── app/
    ├── boot.py
    ├── network_boot.py
    ├── main.py
    ├── device_config.example.py
    └── secrets.example.py
```

Copy locally when used:

```text
device_config.example.py → device_config.py
secrets.example.py       → secrets.py
```

`device_config.py` and `secrets.py` Ignored by Git. Hotspot name, password and WebREPL password cannot be written to an example, VS Code job, log or submission.

The device starts in the following order:

```text
boot.py → network_boot.start()
        Read localsecrets.py
        Time-bound Wi-Fi connection
        ♪ Start WebREPL
        {\cHFFFFFF}{\cH00FFFF} Continue to access the device, whether it succeeds or fails.py
```

The network module does not initialize CAN, Electro, UART or rudder. Wi-Fi failure will be timed out in about 20 seconds, and will not prevent chassis applications from continuing to start. `boot.py` Restore from the complete backup in the ignore directory.

## 7. Separation of formal controls from WebREPL

```text
Development and deployment: VS Code → WebREPL → ESP32 file system/REPL
Formal control: Unified console Control Protocol ESP32 chassis service
```

WebREPL is not an official chassis control protocol. Release mode should shut down or restrict WebREPL, without affecting chassis connection-health polling, stopping, status, or control services.

## 8. Version status of existing chassis programs

Eleven chassis Python files from device backup saved to the original `src/esp32/legacy/chassis_2026_08_31/`, and document by document SHA-256. The directory is only for retroactive and selective migration and cannot be deployed directly.

I'll see you in a static audit. [`legacy-chassis-audit.md`](legacy-chassis-audit.md)...with examples of unknown operating mode auto-executing motion that is allowed to write at non-zero speed after failure, import of initialised hardware and reconnected parking is a block before subsequent migration.

Default established for the first selective migration `SAFE_IDLE` It's got nothing to do with hardware. Design and 12 fake MotoBus regression tests. [`chassis-safety.md`](chassis-safety.md)...and then the official MotoBus moved through 10 fake CAN frames and rollback tests. [`motor-can.md`](motor-can.md)... two parts of a total of 22 tests that have not yet been connected to real CAN or deployment device.
