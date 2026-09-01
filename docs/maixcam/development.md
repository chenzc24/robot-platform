# MaixCam Development Environment

- Device: MaixCam Pro
- Device name:`maixcam-6c7d.local`
- System: Buildroot 2023.11.2, Linux 5.10.4,`riscv64`
- Python: 3.11.6
- MaixPy API: 4.12.5
- Network development: computers and device connected to the same 2.4 GHz hotspot

## 1. Development modalities

MaixCam uses the "VS Code Local Editor + SSH/SCP Remote Run" mode:

```text
Local Git Source (only credible)
        │VS Code Call scp
        ▼
/ root/robot-platform/ (device deployment catalogue)
        VS Code calling ssh
        ▼
    Python running and terminal log
```

Do not use VS Code Remote-SSH to open the remote working area. MaixCam Pro is a RISC-V 64-bit device with about 128 MB memory; Microsoft Remote-SSH does not provide riscv64 support, and remote resources are below its recommended value. Attempting connection will require the installation of unrun VS Code Server.

The project does not rely on Maix Vision or a third party MaixCode Extension. Video is exported from MaixCam's original RTSP service, is directly validated by the computer using PyAV and forwarded to the follow-up console via the FFmpeg non-conformable bridge; device found, source code deployment, start-up and log harmonization of standard web tools.

References:

- [MaixCAM starts fast.](https://wiki.sipeed.com/maixpy/doc/zh/README_MaixCAM.html)
- [MaixCAM RTSP video stream](https://wiki.sipeed.com/maixpy/doc/zh/video/rtsp_streaming.html)
- [VS Code Remote-SSH requirements](https://code.visualstudio.com/docs/remote/ssh)

## 2. SSH entrance

The SSH configuration uses aliases:

```text
robot-maixcam
```

It connects by mDNS device name, does not depend on a potentially variable DHCP address, and uses a project-specific Ed25519 key. Private keys and real network certificates are kept only on the machine and do not enter the repository.

Command line validation:

```powershell
ssh robot-maixcam
```

If mDNS is temporarily disabled, confirm IP on the device Setup Device Information, then sort out the hotspot client exchange; do not encode temporary IP to business code.

## 3. VS Code mission

Select from Terminal Run Task:

- `MaixCam: Check SSH`: Read-out device identity, system and version files.
- `MaixCam: Upload probe`: Create an independent deployment catalogue and upload non-motion probes.
- `MaixCam: Run probe`: After uploading, execute the probe and read back the JSON state on the device.
- `MaixCam: SSH terminal`: Open interactive device terminals.

The probe does not import `maix`MaixPy 4.12.5, even if only executed `import maix` The default communication protocol will also be initialised and will take UART0, so read-only diagnosis should avoid importing the package.

## 4. Device cataloguing boundaries

- `/root/robot-platform/`: Catalogue of independent development and deployment of the project
- `/maixapp/`: System applications and installed applications; read-only at this stage.
- `/boot/`System startup and network configuration; read-only at this stage.
- `src/maixcam/`Locally credible source code.
- `device-backups/maixcam/`: Locally ignored device backup.

Current Device Self Start Application As `num`... this objective does not change self-start, does not cover `/maixapp/apps/`Nor does it run the original serial or robot arm case.

## 5. Backup and recovery available

Cannot initialise Evolution's mail component.

```text
device-backups/maixcam/2026-08-31-maixcam-6c7d-preconfig/
```

Backup contains `/root`, `/maixapp` and `/boot`872 files and generate local SHA-256 lists. Backup contains Wi-Fi configuration and device data, which cannot be submitted or sent externally.

Restoring priority:

1. When SSH is available, restore individual applications or configurations from backup options.
2. Reconfigure by device screen when Wi-Fi is not available.
3. When wireless is not available, use the USB virtual network adapter to connect to SSH.
4. Only when the system is damaged and the previously mentioned path fails will the TF card be re-painted using a firmware image in the read-only database.

## 6. Not yet accessed

- Visual recognition, calibration and image overloading; see base RTSP video link [`video.md`](video.md).
- MaixCam's UART link to ESP32.
- MaixCam's UART link to TCP232/Mechanic arm LAN1.
- Unified console status and video interface.

(b) Any test that may trigger a chassis or robot arm movement must be upgraded to the L3/L4 security door.

Robot arm LAN1 diagnostic program, one-time fixed action, UART0 occupancy protection and VS Code entrance.
[`../robot-arm/lan1-diagnostic.md`](../robot-arm/lan1-diagnostic.md)The portal is only available for users
Confirm that the robot arm diagnostic project is operational and that the corresponding L2/L3 site safety conditions are met;
Launcher, release `/dev/ttyS0`, restore launcher. motion in exit processor after a single request
The request does not automatically retry, and the results are not known until the actual condition of the arm is manually confirmed.
