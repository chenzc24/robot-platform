# MaixCam development channel configuration

- Status:`completed`
- Responsible: Agent execution, user responsible for device screens and necessary physical operations
- Highest validation level:`L2`

## Objective

Without generating a chassis or robot arm movement, connect MaixCam Pro to the existing 2.4 GHz development hotspots, identify the device, system with MaixPy version, create a reusable SSH/SFTP channel for computers and VS Code, and maintain any current application of pre-writing backup devices and associated configurations. MaixVision is reserved only for discovery, preview and recovery, not as a unique source of code I'm not sure.

## Initial state of the workspace

```text
## main...origin/main
 M .vscode/settings.json
```

`.vscode/settings.json` There is an unsubmitted MicroPython button configuration, which is unknown and may be the current editor of the user; this goal is treated as a read-only user modification, without covering, without saving, without submitting. The rest of the workspace is clean.

## Modifyable scope

- `plan/2026-08-31-maixcam-development-channel/plan.md`
- `plan/log.md`
- `docs/maixcam/`
- `src/maixcam/`
- `tests/maixcam/`
- `.vscode/tasks.json`(only without relying on or overwhelming existing settings)
- Git ignored it. `device-backups/maixcam/` Configure files with MaixCam
- `C:/Users/90590/.ssh/id_ed25519_robot_maixcam`, corresponding to the public key and `C:/Users/90590/.ssh/config` Independent `robot-maixcam` Host Session
- MaixCam Devices: Wi-Fi, SSH public key only, develop catalogues and non-motion diagnostics; must be read and backed up before writing

## Read-only

- `.vscode/settings.json` Other Organiser
- `Camera/` Source, firmware image, install package and case code
- `ESP32/`, `Robot Arm_Claws/`, `src/esp32/` And real ESP32
- Robot arm, TCP 232 and chassis hardware
- MaixCam solid, partition and drive; this target does not burn mirrors, does not upgrade systems

## Share dependency and known facts

- MaixCam Pro is the only operational gateway between visual and robot arm; it connects ESP32 through independent UART and LAN1.
- The original course gave UARTPORT a 115,200 rate, but this target was not connected or sent business orders.
- Official documentation supports connection to LAN Wi-Fi or USB virtual network adapters; SSH/SFTP port is 22, device name and IP can be viewed in Setup Device Information.
- Hotspots, SSH passwords and private keys cannot enter Git, log or device backup list output.

## Implementation steps

1. User confirm device models on MaixCam screen, start normal and current device information.
2. Connect MaixCam to an existing 2.4 GHz hotspot, recording local IP/device names but not submitting genuine documents.
3. (b) Read-only collecting system, MaixPy, storage and running process information.
4. Backup the current variable configuration and user application to Git ignore directories before any device is written, and record the list of documents and validation values.
5. Create independent SSH keys or other recoverable VS Code Remote-SSH channels; do not store passwords or private keys in repositorys.
6. Create Local `src/maixcam/` Minimum entrance and non-motion probes, deployed through SFTP to an independent development catalogue to validate logs and document retrieval.
7. Write configurations, restore and use documents daily; do not activate serial controls other than cameras, do not trigger chassis or arm movements.

## User needs assistance

- Power MaixCam and confirm screen access to functional interfaces.
- Select the existing hotspot and complete the connection in the device "Setting WiFi".
- Inform the device name and IP that is displayed in Setup Device Information; confirm that SSH is entering for the first time or handles authorization tips on the screen, if necessary.
- This target does not need to connect to a robot arm, TCP 232 or ESP 32, or a motor safety door.

## Validation

- L0: Document, JSON/Python syntax, Secret scan,`git diff --check`.
- L1: Local MaixCam has no hardware code or deployed script testing (if added to this target).
- L2: Device found, TCP 22, SSH read-only command, SFTP backup/validation, independent directory minimum motionless program running and logback.
- Run on completion `git status --short --branch`, only temporary target ranges, recording outstanding items and residual risks.

## Restore Path

- Reconfigure the network using device screens when SSH or Wi-Fi fail.
- When wireless links are not available, use USB virtual network adapters to help MaixVision or SSH recover.
- Write to an independent development directory and SSH authorization only; remove new content and restore the image of the system.
- Local backup and original firmware images are kept in Git ignore directories and read-only databases.

## Actual results

- Device found in mDNS `maixcam-6c7d.local`, the current IPv4 is dynamic; ICMP, TCP 22 and OpenSSH handshake passed.
- Read-only confirmation of Buildroot 2023.11.2, Linux 5.10.4,`riscv64`, Python 3.11.6 and MaixPy API 4.12.5; device is about 29 GB storage, using about 5%.
- Full Backup Before Configure `/root`, `/maixapp` and `/boot` To the Git ignore directory, the remotes and local files are 70, 775, 27, respectively, and generate 872 files SHA-256.
- Generate a project-specific Ed25519 key, the device was not available `/root/.ssh`; checking secure login via BatchMode with a single public key installed. User SSH configuration added `robot-maixcam` Alias, use mDNS instead of dynamic IP.
- After checking the official requirements, it was confirmed that VS Code Remote-SSH did not support riscv64 and that the device was inadequate, so the structure "VS Code Local Editor + OpenSSH/SCP Mission" was not built with VS Code Server or third party MaixCode expansion.
- Add None `maix` Imported probes, 2 local tests and 5 VS Code missions;
- During the validation period, the device briefly exited the hotspot, and neither the computer side mDNS nor the old DHCP address was available;`maixcam-6c7d.local` Once again, the device, the dedicated key login, the SCP upload, the SHA-256 verification and the probe operation are restored. The result confirmed that the application file and SSH authorization were not lost due to a common network offline, but the hotspot connection itself is not a secure or real-time link.
- MaixVision 1.2.2 has been activated; AutoUI control has been stopped because the user operates the window at the same time, device connection and real-time video previews are kept for manual confirmation.

## Outstanding matters

- MaixVision device connections and real-time images have not yet been validated.
- This target does not change the default system password; although a dedicated key has been used, the exit code is still a residual risk on the development hotspot and should be changed separately after the user has confirmed the recovery.
- Not yet migrated for visual applications, camera preview, ETS32 UART or UART gateway.
- `import maix` The default UART0 communication protocol will be initialized; follow-up visual services must explicitly process the occupancy and complete port ownership design before the connection.
- The third-party MaixCode extension has not yet completed the source code and permission audit and is therefore not installed.

## Intent to submit

```text
feat: establish MaixCam VS Code development channel
```
