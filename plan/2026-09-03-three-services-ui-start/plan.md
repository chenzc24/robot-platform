# Restore the three device routes and open the console

- Status: completed; all runtime routes available, operator motion not exercised
- Baseline: c313e88, target/chassis-hold-release-fix
- Request: keep ESP32, MaixCam and robot-arm services running and start the UI.
- Risk/validation: L2 connection/status and non-motion service startup only.

## Workspace ownership

Preserve user .vscode/settings.json, prior XYZ diagnostic log/plan, and the
independent arm-yz-drawing-review directory. They do not overlap runtime sources.
Editable: this new plan, only this goal's appended plan/log.md section and ignored
local operational logs/helpers. Stage only this new section of the shared log.
Read-only: all production code, protocol, configuration, resource archives,
device files and the other plans. No code/firmware deployment or branch switch.

## Operations and limits

Inspect existing PC sessions first. Reuse healthy services and their ownership;
do not compete with an active console socket or stop unrelated tasks. Connect
ESP32 through the existing PC backend and arm through MaixCam. Start an absent
MaixCam video/gateway only using reviewed deployed non-motion launch scripts.
Start a missing PC relay/backend with existing configuration/credentials kept
out of logs. Open localhost UI and check video availability plus command status.

Do not Enable, jog, grip, home, reset alarms, reboot devices or change network,
limits, UART/TCP232 or taught points. If the controller project is absent or
paused, identify the evidence and ask the operator to start the deployed service
through DobotStudio; do not guess a remote project-start command. If ESP32 needs
REPL/reset with potential legacy startup motion, stop for coordination.

Validation: healthy/disabled-or-existing chassis state, arm PING/STATUS and
feedback availability, MaixCam video/gateway processes, local relay/UI endpoint;
no L3 movement. Record actual failures separately. Review diff/status and commit/
push only this operational record on the current branch, no merge to main.

## Actual operations and results

- Reused PC web PID 34424 on localhost:8080; no backend restart or source change.
  Initial chassis session was offline after a historical TimeoutError; connecting
  through the existing backend authenticated successfully and reported disabled.
- The legacy robot status/connect CLI reported WebREPL unavailable. This is a
  maintenance-port issue, not a failed production route: ESP32 TCP 8765 returned
  runtime state successfully. No REPL, reset, USB or firmware operation was used.
- MaixCam had launcher/supervisor but no arm gateway or video after reboot.
  Confirmed UART0 belonged to launcher PID 688, then compared the deployed guarded
  arm startup script SHA-256 to local source (match). Started that existing guard;
  arm gateway PID 777 and camera RTSP PID 787 became active. No deployment or
  unrelated process kill; the guard only released its verified launcher owner.
- The robot-arm project was already waiting for commands. PC arm connect/STATUS
  traversed the restarted MaixCam gateway and returned controller online/ready,
  YOLO, last_error=none and valid measured six-joint/six-pose feedback. Subsequent
  samples advanced from 1 to 21. No controller restart, alarm reset or motion.
  Used the existing UI session's status path instead of a competing CLI socket.
- Remote camera startup succeeded, but local relay start initially failed because
  MediaMTX remained alive while its old FFmpeg publisher had exited after link
  loss. Restarted only that managed local relay: MediaMTX PID 8308, FFmpeg 25524.
  The MaixCam/video/gateway processes remained running during this relay recovery.
- MediaMTX path maixcam reports ready=true, online=true, H264; bytesReceived grew
  from 5,802,392 to 16,632,156. FFmpeg decoded one actual relayed frame to null
  successfully with the locally documented RTSP -timeout option. An initial
  probe used unsupported -rw_timeout and exited without opening input; corrected
  the diagnostic command only, not product code.
- UI root returns HTTP 200. Requested the Codex browser panel to open localhost;
  the app reported queued, so window visibility is not asserted. UI backend and
  assets are available immediately at http://127.0.0.1:8080/.
- Final runtime state: ESP32 online/disabled/idle; arm gateway/controller online,
  ready/YOLO with valid feedback; video receiving. Retained the old acknowledged-
  false chassis TimeoutError history instead of silently clearing it; current
  chassis reports last_error=none. No Enable, velocity, jog or gripper sent.
- L2 checks above passed; L3/L4 not run. Only this plan/log entry and ignored
  operational PID/log files changed. Diff/status validation and scoped push
  preserve all pre-existing settings, XYZ diagnosis and YZ drawing-review work.
