# Console Arm UI L2 Acceptance

- Status: `completed`
- Responsible: `joint`
- Highest validation level: `L2`

## Objective

Verify that the current Hardware-mode desktop console connects to the deployed
MaixCam arm endpoint, requests and renders arm status, records a journal entry,
and preserves locked arm-motion controls without issuing any state-changing
command.

## Initial workspace state

```text
## main...origin/main
```

The MaixCam arm CLI passed five consecutive non-motion checks. LAN2 is
disconnected and the deployed controller service remains default-deny.

## Editable scope

- `plan/2026-09-02-console-arm-ui-l2-acceptance/plan.md`
- `plan/log.md`
- directly affected console UI/runtime code and focused tests only if this
  acceptance test exposes a defect
- `src/console/ui/views.py`, `src/console/ui/controller.py`, and direct tests
  to replace the overcrowded hardware arm panel with an honest runtime-route
  mapping; no motion admission implementation is included

## Read-only scope

- ignored local configuration, endpoint addresses, credentials, all device
  configuration, ESP32, TCP232, arm controller project, raw-resource archives,
  and the separate primary-worktree user changes

## Dependencies and safety

- Hardware route: computer -> MaixCam TCP 8780 -> UART0 -> TCP232 -> arm LAN1.
- Only UI connect and `arm.status` are permitted. No chassis action, arm motion,
  controller configuration, LAN2 operation, or expected-rejection probe is in
  scope.
- No L3 authorization exists. The UI must keep all arm motion controls disabled.
- Hardware UI must not expose simulator-only joint, Cartesian, or gripper forms
  as if they were operational. It must show the endpoint route, status age,
  admission state, and the precise reason that motion is unavailable instead.

## Validation

- L0: diff and workspace status checks.
- L2: start the local console, select Hardware, connect the arm route, verify
  a current `ready/motion_enabled=0` status in the panel and journal, then close
  the console without sending any motion request.

## Actual results

- The initial Hardware-mode run connected to MaixCam and received a terminal
  status reply, but the arm panel retained `UART/LAN1=Unknown` and
  `Controller=Unknown` with `invalid_arm_status_terminal`. CLI checks against
  the same endpoint remained ready, so the route itself is not the cause.
- Root cause: the generic runtime wrapper marked every successful socket return
  as `DONE`, even when the nested MaixCam terminal lifecycle was
  `REJECTED/request_in_flight`. The UI then attempted to parse that rejection as
  a successful status envelope. The wrapper now emits an explicit rejection and
  retains the healthy session; a focused L1 regression test passes.
- The runtime now inspects the nested MaixCam terminal lifecycle before
  constructing its outer lifecycle event. A nested rejection is shown as a
  rejection, rather than being parsed as a successful arm-status envelope.
  The Hardware view hides simulator-only motion forms and shows an explicit
  default-deny explanation instead of a misleading usable-looking control.
- L1: `python -m unittest discover -s tests\\console -v` passed all 47 tests.
  Python compilation of the changed UI/runtime modules and `git diff --check`
  also passed.
- L2 visual rerun: a newly started console was switched to Hardware and only
  **Connect arm route** was used. The panel rendered MaixCam **Online**,
  UART/LAN1 **Online**, Controller **Online**, and Task **Idle / ready**. It
  rendered `Route ready; controller policy is default-deny (motion_enabled=0).`
  and kept the `Hardware motion unavailable` control disabled with all
  simulator joint/Cartesian/gripper forms hidden. No arm motion or controller
  configuration command was sent.
- The concurrently displayed ESP32 connection and video-decoder faults were
  pre-existing out-of-scope statuses; there was no arm-route fault following
  the L2 connect/status refresh.

## Outstanding matters

- Hardware arm motion is deliberately not implemented in this console release.
  A separate L3 goal needs an approved action mapping, arm bounds/safe poses,
  low-speed validation, and an explicit on-site safety gate before the UI may
  send an arm command.

## Intent to submit

```text
test(console): accept arm UI L2 binding
```
