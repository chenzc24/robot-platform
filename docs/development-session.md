# ESP32 Integrated Development Meeting with MaixCam

- Status: Development period implementation baseline
- Scope: Computers, ESP32-S3, MaixCam and mobile phones Hot.
- Does not contain: robot arm motion, chassis motion command and final control Station

This document records the day-to-day development path that has been validated by a genuine machine. First installation, day-to-day connection, code deployment and failure recovery must be separated; Daily connection does not repeat brushing solids, upload source code or modify system configuration.

The day-to-day interaction goes through two layers:

```text
robot CLI / VS Code
        ↓
Connection Management: Discovery, Magnetic Start, Single instance lock and process attribution protection
        ↓
Abnormal feedback: READY / DEGRAD / OFFLINE, error code and next suggestion
```

## 1. Two device links

### 1.1 ESP32 Development links

```text
VS Code Local Source
  ├ USB / mpremote / esptool first configuration, backup and recovery
  └-Wi-Fi/ WebREPL upload, reboot
                                      ↓
                                ESP32 MicroPython
```

U.S.B. is the restoration of the channel, not the condition of routine wireless development. WebREPL is the development of the deployment channel, not the final chassis control protocol.

### 1.2 MaixCam development and video link

```text
Underline code: VS Code → SCP → / root/ robot-platform/ → SSH stop/ log

Video: MaixCam RTSP/H264
          FFmpeg-c:v copy reassembly
          → MediaMTX
          RTSP / HLS / WebRTC
```

SSH/SCP and RTSP are two separate planes: the former manages the code and process, and the latter transmits video on an ongoing basis.

## 2. Daily start-up process

### 2.1 Public networks

1. Turn on the configured 2.4 GHz phone hotspot, turn off automatic hibernation.
2. Computer connection hotspots.
3. (b) If the chassis is powered simultaneously, make sure that it is in a state of failure, emptiness or other agreed safety.
4. Waiting for two devices to get DHCP addresses.

### 2.2 Unified connectivity

Execute in the repository root directory:

```powershell
.\robot connect
```

There is only one line summarizing the normal result:

```text
READY  maixcam=online  esp32=online  camera=online  video=online
```

The order operates at the following boundaries:

- Prefer to the last successful address and the ARP active candidate finding ESP 32, which failed to conduct a peer scan.
- Check only ESP32 WebREPL port, do not log in, do not upload files, do not return.
- When MaixCam SSH is online and RTSP is missing, only existing project start-up scripts on the device are called, no source code is used, no other program is stopped.
- (b) Healthy services remain intact.
- Only one at the same time. `robot` operations; second operation returns `operation_locked`.

Anomalous execution:

```powershell
.\robot details
```

CLI uses a three-tier general state:`READY`Indicates that all is available;`DEGRADED`This means that at least one device is online but that one service is unusual;`OFFLINE`Means that infrastructure is not available. All orders can be added. `--json` For the follow-up console.

### 2.3 ESP32 development operation

1. Confirm the current IPv4 of ESP32 from the list of hotspot clients
2. Runs only when deployment or REPL is required `ESP32: Open WebREPL browser client`.
3. Enter on the official WebREPL page `ws://<esp32-ip>:8266/` And the codes that we keep.
4. Close the other WebREPL sessions, and flyer a reviewed document.
5. Assume current before entering REPL `main.py` (b) Any repositioning must consider the possibility of re-initiation of the PS2/CAN program on the device.
6. Disconnect WebREPL after debugging.

At this stage, there is no ESP32 wireless batch upload, atomic switching and a one-key process for health checks; manual WebREPL uploads are not allowed to be presented as a completed automatic deployment channel.

### 2.4 MaixCam development operation

1. Daily connection usage `robot connect`, do not carry out uploading for start-up service.
2. When MaixCam restarts, if CLI reports that the camera is occupied, exits the device screen from startup `num` Apply, retry the connection.
3. Only if the source code changes. `MaixCam Video: Start RTSP`Deployment.
4. Run `MaixCam Video: Open WebRTC`Turn it on.
5. Run only when the image is abnormal `Probe direct` and `Probe relay`Do an in-depth media check.

Current manual acceptance results: WebRTC's actual video stream is normal; the image eventually shows that the direction should rotate 90°. rotation has not been implemented, which is the target for subsequent display and coordinates.

## 3. Daily closure process

1. Disconnect ESP32 WebREPL sessions, leave no interactive RREPL long-term occupancy running program.
2. Run `.\robot disconnect`: Only computer-side FFmpeg and MediaMTX.
3. If MaixCam is still running the power supply, it will not stop and restart the RTSP on a daily basis; it may not be possible to re-initiate the camera in the same opening speech.
4. If you're ready to lose power, you can run first. `MaixCam Video: Stop RTSP`And then they shut down the power supply.
5. When any real chassis or robot arm operation is completed, the performance of its L3/L4 target failure, the security position and the physical stop inspection;

## 4. Detachment

| phenomena | Check first. | Processing |
|---|---|---|
| ESP32 cannot connect to WebREPL | Hotspot Client List, Current IPv4, TCP 8266 | Confirm power on device and Wi-Fi; read through USB as necessary `WLAN.ifconfig()` |
| WebREPL connection or upload denied | Is there another WebREPL session? | trying again after closing an old session;do not output password in log |
| ESP32 debug main application not running | Whether or not REPL interrupts `main.py` | Revert under safe conditions, confirm the status of the original application on site |
| MaixCam SSH failed | Hotspot, mDNS and current device IPv4 | confirm network on device screen; not write temporary IPv4 to Git |
| RTSP startup failure/cam busy | `num`or other cameras | Exit occupancy application, make sure only one camera owner |
| RTSP log appears `No buffer space available` | Whether to restart the camera after the same launch. | Stop residual process and physically restart MaixCam, then quit. `num` |
| Original RTSP is normal, but forwarding no image | Whether FFmpeg and MediaMTX run simultaneously | Run `Stop PC relay`Later. `Start PC relay`;not changing to MediaMTX direct pull |
| MediaMTX Path `ready`But bytes are 0 | FFmpeg publicsher state | View `logs/mediamtx/ffmpeg-stderr.log`;must use `-c:v copy` Reassembly |
| This machine RTSP/HLS is normal, WebRTC page abnormal | Browser and WebRTC Session | First. `Probe relay` Confirm the media layer, and check the browser separately. |

## CLI Maintenance Command

Daily only `connect/status/details/disconnect`... the following orders shall be used only for the purpose of maintaining clearly:

```powershell
.\robot ps relay
.\robot ps maixcam
.\robot logs relay
.\robot logs maixcam-video
.\robot stop relay
.\robot restart relay
.\robot stop maixcam-video
.\robot restart maixcam-video
.\robot kill maixcam-video --force
.\robot reboot maixcam
```

Maintenance of protection:

- Accept only a fixed target name, without providing any PID or `killall`.
- MaixCam validates PID as a number before the video is terminated, processes exist and command lines belong to the item `rtsp_server.py`.
- `kill`It must be given at the same time. `--force`and cross-confirmation; automation also needs visible additions `--yes`.
- MaixCam restart requires interactive confirmation or `--yes`; may still require manual exit after restart `num`.
- `robot reboot esp32`Keep locking, because the device still deploys the old PS2/CAN program, repositioning may initiate motor hardware.
- MaixCam video returned when the same reboot failed `camera_reinit_failed`The next step is to restart the whole machine, not automatically to kill.

Exit code fixed to:`0`Success or READY;`1`Anomalous or DEGRADED/OFFFLINE;`2`Parameters/environment errors;`3`The rules of protection are rejected.

## Arm endpoint diagnostics

Use the same flat CLI for routine MaixCam-to-arm-route diagnosis. These commands
open one direct computer-to-MaixCam TCP session, print a concise terminal result,
and close the session; they do not start the desktop UI or require LAN2.

```powershell
.\robot arm ping
.\robot arm status
.\robot arm check
.\robot arm check --json
```

`check` sends exactly one `PING` followed by one `STATUS` on the same session.
It is the first check when the arm card or console reports offline. Override a
temporary discovery result locally, without editing committed configuration:

```powershell
.\robot arm check --arm-host 192.0.2.40 --arm-port 8780 --json
```

The separate expected-rejection proof is deliberately named so it cannot be
mistaken for an arm-motion command:

```powershell
.\robot arm reject-motion --json
```

It submits one syntactically valid zero-joint request and succeeds only when the
MaixCam endpoint returns `REJECTED/admission_rejected` before UART output. It
never retries. If it returns any other result, do not issue further arm commands;
inspect the MaixCam admission configuration. This remains L2 validation, not
authorization for arm motion.

## 6. Registration of issues

| Problem | Status | Current decision-making |
|---|---|---|
| ESP32 DHCP address variable | Known constraints | Read from the cell phone list or USB, uncoded |
| ESP32 WebREPL address, password and upload still manual | To be improved | Retain official client; follow-up secure wireless deployment targets |
| WebREPL allows only one active connection | Known constraints | Close an old session before connecting and uploading |
| REPL can interrupt the ESP32 chassis `main.py` | Security constraints | debug and reset and confirm on site; not using WebREPL as a formal control protocol |
| MaixCam self-starts `num` Camera occupancy | Manual step | exit after each restart; without permission to modify self-start |
| MaixCam camera failed to restart the same session | Unsolved | avoiding daily recurrence;physical restart at occurrence |
| mDNS select not available IPv6 | Solved | RTSP probe and repeater Visible Resolution IPv4 |
| MaixCam H.264 Mode 0/FU-A is incompatible with MediaMTX | Solved | FFmpeg `-c:v copy` Resealed as publicsher |
| VS Code Remote-SSH does not support device RISC-V environment | Rounded | Local VS Code Editor, Standard SSH/SCP Deployment |
| Video needs a clockwise rotation of 90° | Confirmed, not implemented | Harmonize processing in display and visual coordinates |
| Hotspot-wide scan for occasional eSP32 | Solved | Prioritize Cache and ARP active candidates, low- and bottom-scan |
| Start computer relay and CLI does not quit | Solved | External command output changed to temporary file to avoid FFFmpeg/MediaMTX inheritance capture conduit |

## 7. Restoration of access

- ESS32 Wireless: using USB and `mpremote`read running and network status;do not default on Flash.
- MaixCam's Wireless: Restore SSH using device screens or USB virtual network adapters.
- MaixCam Media Drive Failed: Physical restart, exit `num`And in the normal order.
- Device file damage: controlled source code from Git or `device-backups/` Ignored backup selectively restores, does not cover unverified system directories.
