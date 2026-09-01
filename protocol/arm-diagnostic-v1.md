# Arm diagnostic protocol v1

This validation-only protocol verifies the MaixCam UART to PCB TCP232 to arm
LAN1 path. It also contains one tightly bounded L3 command; it is not the
future general arm motion protocol.

Each frame is one ASCII line:

```text
RPA1|TYPE|SEQUENCE|PAYLOAD|CRC16\n
```

- `RPA1` is the fixed marker and version.
- `TYPE` is `PING`, `PONG`, `STEP`, `DONE`, or `ERROR`.
- `SEQUENCE` is a decimal integer from 1 through 2147483647.
- `PAYLOAD` is empty for `PING`, `PONG`, `STEP`, and `DONE`. `ERROR` contains one lowercase
  token made from `a-z`, `0-9`, and `_`.
- `CRC16` is four uppercase hexadecimal digits. It is CRC-16/CCITT-FALSE over
  every ASCII byte before the CRC field, including the trailing `|`.
- A complete frame is at most 96 bytes including `\n`.
- `\r`, whitespace, non-ASCII data, extra fields, and oversized input are
  invalid.

The MaixCam sends one `PING` and accepts only a matching `PONG` before the
bounded timeout. After a separate on-site L3 safety confirmation, it may send
one `STEP` and accept only a matching `DONE`. `STEP` has no motion parameters:
the arm-side project hard-codes J1 +1 degree, a one-second wait, then J1 -1
degree, at 5 percent speed and acceleration with blending disabled. Each arm
project run consumes at most one `STEP`; duplicates return
`motion_already_consumed`. The MaixCam never retries it automatically.

A matching `PONG` proves bidirectional application data across the UART,
TCP232, LAN1 TCP session, and arm program. It does not authorize motion. A
matching `DONE` reports that the controller program issued both bounded motion
segments; the on-site observer remains responsible for confirming actual
motion and return to the safe pose.
