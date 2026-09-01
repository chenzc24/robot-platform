# ESP32 PS2 Control Access Low Speed Truth Test

- Status:`completed`
- Agent is responsible for wireless start-up and recording, and the user is responsible for site security and handle operations.
- Highest validation level:`L3`

## Objective

Without modifying the device file, re-enter the existing PS2 main program for the ESP32 via certified cell phone hotspots and WebREPL, with users testing the handle-ESP32-CAN-wire access, parking keys and power failure keys under empty or reliable limit conditions.

## Initial state of the workspace

```text
## main...origin/main
```

Workspace clean. ESP32 current address. `10.114.1.97` ICMP and TCP 8266 are available; USB has been removed.

## Modifyable File

- `plan/2026-08-31-esp32-ps2-path-test/plan.md`
- `plan/log.md`
- ESP32 operational state: perform remote hard-to-do position only once after security door confirmation

## Read-only files and directories

- Repository full source code and configuration
- ESP32 Filesystem
- Source directory and device backup

## Shared Dependencies

- ESP32 Existing `RUN_MODE="ps2"` Main program.
- Cell phones hot, WebREPL and current DHCP address.
- PS2 Map: Right Roller Control Horizontal, Left Roller X Control Rotation, R1 Stop, X Deactivation, Triangle Re-enactment, SELECT exit.
- Historical source security risks documented but not repaired.

## Manual security doors

The user must clearly confirm all conditions of this round before starting:

1. Personnel present and capable of immediately operating the physical stoppage or disconnection of electrical power.
2. The chassis four wheels are empty, or the chassis has a reliable mechanical limit in the agreed safety zone.
3. There are no people around the chassis, cables and barriers;
4. The PS2 handle is in the middle. Users know R1 parking, X power failure and physical power outage.
5. The following actions and suspension conditions are agreed: only small, short-time single-axis inputs; any on-the-spot, directional abnormality, continuous movement, failure to connect or non-validity of the key, immediate physical stoppage/cut off and termination of the test.

## Expected steps

1. Once the security door is confirmed, we'll do it through WebREPL. `machine.reset()`- The order will be disconnected.
2. Waiting for start-up and only checking ICMP and TCP 8266 to resume, not enter the RSL interference PS2 main program.
3. Users press X-deactivated, then Triangle re-activated.
4. User size in turn, short-time test before and after, transverse and rotate, and take it back to the middle.
5. User test R1, stop and end with X-ray failure.
6. User report results per step; Agent does not send any speed or motion commands.

## Validation

- L2 foreword: ICMP and TCP 8266 to reach.
- L3 site: electrostatic, PS2 axis, roller-back stop, R1, X-deactivation, Triangle power.
- If you fail, you record the facts, you don't continue to expand your movement or speed.
- `git diff --check`
- `git status --short --branch`

## Actual results

- Users have confirmed five L3 site safety conditions.
- It was sent once through WebREPL. `machine.reset()`; ICMP and TCP 8266 are restored in 12 seconds, indicating that the network guidance and main startup process has been restarted.
- Users complete the PS2 site test in the sequence and report success: incompetence, re-enabling, small single-axis chassis control, roller back, R1 parking and final failure access.
- Agent only performs remote reset and network recovery checks without sending speed or motion commands; all actions are triggered by live users via PS2 handles.

## Outstanding matters

- This wheel does not verify network controls, tracks, cameras UART, rudders or robot arms.
- The current round does not repair the problem of the stationary audit.
- The conclusion of this round only proves that the current PS2 manual control route is available, does not prove unknown patterns, missing connections, autonomous tracks, network controls or drive feedback secure.

## Intent to submit

```text
test: record ESP32 PS2 hardware path validation
```
