# ESP32 Hotspots with WebREPL

- Status:`completed`
- Responsible: Agent execution, users providing hot spots and site conditions
- Highest validation level:`L2`

## Objective

Connecting to the current MicroPython cell phone 2.4 GHz hotspot through COM7 confirms ESP32's access to the local area network (LAN) address; then configures the independent WebREPL password and validates the wireless REPL connection of the computer to ESP32. Existing startup file is not modified without validation.

## Initial state of the workspace

```text
## main...origin/main
```

Workspace clean. MicroPython 1.27.0 and device file system completed read-only backup; users have turned on hot spots and clearly authorized the use of hot spots provided by this round According to... hot code not to write to Git, schedule, log or command output.

## Modifyable File

- `.vscode/tasks.json`
- `src/esp32/app/boot.py`
- `src/esp32/app/network_boot.py`
- `src/esp32/app/secrets.example.py`
- `src/esp32/app/secrets.py`(Door ignores files)
- `src/esp32/README.md`
- `docs/esp32/development.md`
- `plan/2026-08-31-esp32-wifi-webrepl/plan.md`
- `plan/log.md`
- ESP32 Runtime Network State
- ESP32 directories `boot.py`, `network_boot.py` and `secrets.py`

## Read-only files and directories

- Remaining repository files
- ESP32 Existing chassis application file, unless planned to be clearly updated before writing

## Shared Dependencies

- MicroPython 1.27.0.
- User phone 2.4 GHz hotspot.
- The official WebREPL client and the separate password limit for 4-9 characters.
- Local device file system backup completed.

## Risk and safety door

- Risk:`mpremote`The current PS2 control program will be stopped and reset softly; and the subsequent re-initiation of the CAN and the power is possible.
- Device: ESP32-S3. on COM7
- User Operations: Hotspots are on; on site keep the chassis unplanned.
- Backup and recovery: complete file backup is available before writing; non-sustainable running connection is used first for this round.
- Motion confirmation: Do not send chassis motion orders.

## Expected work

1. Activate STA and connect mobile phone hotspots through the current MicroPython session, without printing passwords.
2. Read the connection and the DHCP address and confirm that the computer and ESP32 are on the accessible section.
3. Determines that 4-9 characters WebREPL are unique passwords, enable and verify wireless terminals by serial port.
4. The Wi-Fi and WebREPL pilot modules will be written into the start-up process after the Wi-Fi and WebREPL are overtimed and abnormally sequestered; real proof only exists that the file and device file system is ignored.
5. Revalidate DHCP, TCP 8266 and read-only REPL after restart; do not change or send chassis motion commands.
6. Replace the official CLI terminal task with the official WebREPL browser client portal, which is not available under Windows and which resonates.

## Validation

- Read `WLAN.isconnected()`, `WLAN.status()` and `ifconfig()`.
- Computer to ESP 32 `ping` Connect to TCP 8266.
- The official WebREPL protocol completes the login and executes a read-only REPL order.
- Repeat LAN and WirelessREPL check after restart.
- `git diff --check`
- `git status --short --branch`

## Actual results

- ESP32 successfully connected 2.4 GHz mobile phone hotspots in the current session.`WLAN.isconnected()`For real, and through DHCP `10.114.1.97/24`- ICMP visits were successful after the computer cut to the same hotspot.
- (b) Official WebREPL protocol completes the clearance, returns MicroPython 1.27.0 and successfully executes the unwritten REPL tag order.
- Add `network_boot.py`, using 20 seconds of roving to connect Wi-Fi and activate WebREPL;`boot.py`Isolation network abnormal, non-initiation of movement outside. `secrets.py` and device documentation systems
- Press `network_boot.py`, `secrets.py`, `boot.py` , and complete the grammatical check of three files at the end of the device; no changes to the original device `main.py` Or other chassis files.
- ESP32 automatically restores the same DHCP address and TCP 8266 service after hard repositioning, wireless validation and read-only RTL probes again succeed. After completion of the probe, executes the final hard reset, confirming that ICMPs and TCP 8266 resume, and no longer enters the RPL to interfere with the original PS2 start-up process.
- A fixed version of the official CLI completed its clearance in Windows due to a lack of information `termios` Quits, and unexpectedly moves back to the CLI password. VS Code has removed the CLI terminal and uploading task and opened it officially `webrepl.html` Browser client.
- Local Python syntax, VS Code job JSON, Official Browser Client Existence, Secret Scan and Git format check.
- This round only performs L2 connection and configuration verification, does not send chassis motion orders, does not perform L3 campaign validation.

## Outstanding matters

- The DHCP address is still subject to change; mDNS or device discovery tools are left to follow-up network diagnostic targets.
- Windows' daily wireless operation currently uses an official browser client to order multi-file synchronization to wait upstream to repair or create a separate target to achieve undisclosed thin packaging.
- Original device chassis `main.py` No audit has yet been conducted to move to version management source code, and the current round remains as it is.

## Experience signal (for manual review)

- A fixed version of the official WebREPL CLI has transportable security/compatibility issues with regard to Windows InteractiveREPLs and certificate output;

## Intent to submit

```text
feat: enable ESP32 Wi-Fi WebREPL bootstrap
```
