# MaixCam to robot arm LAN1 link check.

## Chain

```text
MaixCam /dev/ttyS0 (115200 8N1)
    ↔ PCB TCP232 (TCP Client)
    LAND12.168.5.1:5200 (TCP Server)
```

The robot arm project is located `src/robot_arm/diagnostics/`, Achieved
`protocol/arm-diagnostic-v1.md` Yes. `PING/PONG` And one-time fix `STEP/DONE`.
`point.json` Empty, without initialization, enable, click, track, point or claw API.

`STEP` For L3 link acceptance only: J1 is at 1°, waiting for 1 second, reverse 1°, speed and acceleration
5% each, smooth transition closed. Request does not contain angles, speeds or point parameters;
At the most, MaixCam won't try again. It's not a GEM protocol.

## L2 no motion validation

1. (b) There are no persons or obstacles around the arm of the machine.
2. Connecting DobotStudio through LAN2 to stop old camera communication project. Received `Initialize` or
   `biao...` It's going to carry out the exercise, not as a connected probe.
3. At the DobotStudio project `main.py` Use
   `src/robot_arm/diagnostics/main.py`Check. `point.json` Yes `[]`Start the diagnostic program.
   The program is blocked. `TCPRead` And it means no abnormality is waiting for the TCP 232 input, not the card.
4. Confirms that TCP 232 is 115200 8N1, TCP Client, targeted at robot arm LAN1.
   `192.168.5.1:5200`If the present value is different, it is recorded and stopped, without unauthorized modification.
5. MaixCam side confirmation. `/dev/ttyS0` When no other process is occupied, run an independent L2 probe once.
   Using Linux POSIX serial interface, not importing will automatically start Maix communication protocol `maix` Bag.
6. Only with a correct CRC serial number. `PONG` as pass; any timeout or error stops testing.

By proving a two-way data link, the robotic arm movement is not authorized.

## L3 Fixed Action Validation

1. Identify the current round, stop conditions and fail to process, and confirm that the entity is out of service, around
   Unaccessible, chassis fixed, robot arm secure, low speed and confirmed load.
2. Keep the above `main.py` Run and stop on `TCPRead`(b) Robot arm as required.
3. Deployment `src/maixcam/arm/` After that, through the protected entrance, one time:

   ```sh
   /root/robot-platform/arm/run_guarded_l3.sh EXECUTE_FIXED_J1_STEP
   ```

4. On-site observation of a small rotation of J1, paused for about a second and returned; the machine response must match the serial number.
   `DONE`...unusual and immediate physical stoppage, cannot rely on Wi-Fi or software.
5. Confirm when the probe exits `/dev/ttyS0` Restart
   `/maixapp/apps/launcher/launcher` Hold; Stop DobotStudio project and disable robot arm.

If the operator fails to read the action, do not re-issue it directly. The current robot arm project returns.
`motion_already_consumed`;must stop manually and restart `main.py`, recheck security conditions,
Reauthorization is required for re-execution.

## Verified facts (2026-09-01)

- L2 `PING/PONG` Success, Serial 1, 163 milliseconds.
- L3 fixed motion returned in two separate manual authorisations, two separate robot arm projects in operation `DONE`;
  3525 milliseconds and 3221 milliseconds, respectively.
- After each run, Maix launcher supervisor keeps running.`/dev/ttyS0` The owner returns to
  launcher; did not modify robot arm IP, TCP 232 parameters, security parameters or taught points.

## Common obstructions

| phenomena | Reason or judgement | Processing |
|---|---|---|
| DobotStudio stopped at `TCPRead` | Normal blockage waiting. | Keep running, wait for MaixCam |
| `uart_owner_not_launcher` | Serial occupied by unknown process | If you don't kill, we'll find the owner and continue. |
| Zombie PD after launcher was stopped. | File description may have been released | Here. `fuser /dev/ttyS0` That's right, not just watching. `kill -0` |
| `motion_already_consumed` | STEP has been implemented for this robot arm project | Stop and rerun the project, move back safely The door. |
| STEP timeout or response loss | The action results are unknown | No re-testing, first confirmed from site and physical state. |
| PowerShell expands a remote `$variable` locally | SSH backup path or copy target is incorrect | Wrap the remote script in single quotes, or do not mix local and remote variables in one command line |
