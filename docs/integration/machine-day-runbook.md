# Machine-Day Runtime Candidate Runbook

The default session is L2 and permits no chassis or arm motion. Use the current device identity, release manifest, and rollback copy; never use a DHCP address or credential from Git.

1. Record the on-site operator and emergency-stop operator. Confirm chassis restraint, arm disabled state, clear workspace, current project, UART owner, and rollback route.
2. Verify MaixCam video independently. Do not use a video frame as a motion-safety proof.
3. With ESP32 `tcp_v3_l2`, prove wrong-credential rejection, correct `HELLO/PING/STATUS`, `motion_permitted=false`, connection-health timeout, and reconnect. No CAN object or motor may be created.
4. With the arm RPA2 project default-disabled, prove `PING/STATUS`, valid CRC/sequence, default motion rejection, timeout classification, and UART-owner restoration. No `MOVEJ`, `MOVEL`, or `GRIPPER` is permitted.
5. Stop temporary endpoints, restore normal process owners, record all sequence numbers and final device states.

Before a future L3 round, create a new goal that names the exact policy values, controller behavior, expected motion, speed, stop condition, and recovery action. Obtain fresh explicit confirmation that an on-site operator can use the physical emergency stop.
