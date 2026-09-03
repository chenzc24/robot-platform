# Repair arm web command types and terminal-result handling

- Status: implemented; PC restarted and L2 checked; operator L3 acceptance pending
- Baseline: `4f9e383`; branch `target/arm-ui-command-fixes`
- Risk: L1 integration regressions and L2 PC restart/read-only device queries.
- Dirty audit: preserve user `.vscode/settings.json`. The diagnostic plan and
  `plan/log.md` addition are this agent's preceding diagnosis of these same bugs;
  retain and include them as supporting evidence, not unrelated cleanup.

## Ownership

Editable: `src/console/runtime_core.py`, `src/console/web_console/runtime.py`,
focused/new `tests/console/` regressions, `docs/console/control-console-ui.md`,
this plan, previous diagnosis plan and `plan/log.md`, ignored local helpers/logs.
Read-only: device runtimes, raw resources, protocol definitions, deployment
packages, credentials, user settings, legacy Qt adapter and existing CLI.

Shared contract: RPA2 already defines integer speed/acceleration/gripper values
and ERROR/FAULT responses. No schema/device change is needed. Use real local
protocol, client, gateway and controller service in tests with recording-only
vendor calls. ESP32, video and controller policies stay unchanged. Shared PC
dispatch must only return success on DONE; legacy Qt must no longer see a false
success (its optional runtime suite may be unavailable without PySide6).

## Work and validation

1. Normalize integral numeric fields to int, rejecting fractional/nonfinite,
   boolean or out-of-range inputs without rounding. Preserve real-valued joints
   and pose; leave all approved ranges unchanged.
2. Preserve DONE/REJECTED/FAULT/UNKNOWN outcomes, reject missing/malformed
   terminals, surface device error codes in web events and faults. Explicit
   controller errors do not disconnect a healthy arm socket or chassis.
   Repeated status errors must not flood logs or reset acknowledged faults.
3. Add real-chain tests for all five arm commands, failed controller API,
   gateway rejection, unknown/invalid reply, numeric boundary cases and HTTP
   error responses. Run existing console/dev tests and syntax/diff checks.
4. Inspect current runtime state before restarting only the PC web backend.
   Wait if a command is active. Disconnect sessions using existing APIs, verify
   exact listener/process identity, then replace that process with the existing
   credential-preserving launch helper. Do not change remote services or video.
   Reconnect with PING/STATUS only; no Enable, movement or gripper commands.
5. Record evidence and remaining manual acceptance, stage only declared files,
   commit/push this bounded branch, preserve user settings; do not merge main.

## Actual results

- Updated only PC shared terminal dispatch and web normalization/error mapping.
  Integral values are emitted as int; fractional/nonfinite/bool values are
  rejected before dispatch, with no change to 1..100% / 0..70 mm ranges.
- The shared dispatcher only returns on DONE. Device FAULT/REJECTED reaches
  web HTTP errors, actual lifecycle events and retained fault cards. Explicit
  failures preserve the healthy socket. Motion response loss/malformed results
  become UNKNOWN, disconnect only the arm route and are never retried.
- Status errors are retained without poll-driven log flooding or ACK reset;
  a new failed operator command re-arms its fault. Fault acknowledgement is not
  an additional motion gate. Historical text logs were preserved, not rewritten.
- L1: 73 runnable tests passed (48 console, 25 dev), including 11 new real-chain
  integration tests. All five primitives reached the recording-only API exactly
  once; rejection, controller error, unknown, malformed reply, integer bounds,
  status error persistence, independent chassis health and HTTP errors passed.
  Python compilation and `git diff --check` passed. Two optional legacy Qt
  modules remain unrun because this environment lacks PySide6; no Qt files changed.
- Initial restart attempt was deliberately aborted: after disconnection the
  operator reconnected/Enabled the old chassis session. The user subsequently
  explicitly authorized restarting the backend and paused UI operation.
- Disconnected arm/chassis via their existing APIs (chassis sends STOP/Disable),
  verified the owned old web process 32080 with parent 16080 and command line,
  then stopped only that process. Existing ignored credential-preserving helper
  launched the replacement (launcher PID 38004). No remote service was restarted,
  no device configuration/source changed, and no nonzero command was issued.
- L2 after restart: connected arm via PING/STATUS and chassis via authenticated
  HELLO/STATUS. Arm ready/YOLO with valid measured sample 550; chassis disabled,
  zero requested velocity, approved 600 mm/s and 800 mrad/s envelope unchanged.
- The controller's retained pre-fix `invalid_acceleration` now appears as
  `arm_invalid_acceleration` in faults and the text log, instead of remaining
  hidden. No corrected motion/gripper command was sent to clear it; operator
  physical movement/gripping acceptance remains pending. Services stay running
  at localhost:8080 for manual testing.
- Scoped records and implementation are prepared for commit/push on the goal
  branch. User `.vscode/settings.json` remains untouched and unstaged.
