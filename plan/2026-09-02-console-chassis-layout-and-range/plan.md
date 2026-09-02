# Console Chassis Layout and Manual Range

- Status: `completed`
- Responsible: `agent with user authorization to widen manual debug limits`
- Highest validation level: `L3`

## Objective

Make the chassis panel less crowded and widen the useful attended tuning range
without removing bounded manual limits or changing the default selected speeds.

## Initial state of the workspace

```text
## target/control-console-manual-l3...origin/target/control-console-manual-l3
```

The worktree is clean. A visible console from the prior deployment is running
from committed code and will be restarted only after local validation.

## Modifyable File

- `src/console/ui/views.py`
- `src/esp32/app/chassis_runtime_factory.py` after the deployed 200/400 config
  exposed its stale 100/200 validation ceiling
- `config/console.example.json`
- `config/esp32-l3-device_config.example.py`
- Ignored `config/console.local.json`, manual speed fields only
- Ignored `src/esp32/app/device_config.py`, manual speed fields only after a
  separate immediate deployment gate
- `tests/console/`
- `docs/console/manual-chassis-debug.md`
- `docs/esp32/chassis-tcp.md` if limit documentation requires it
- `docs/overall-plan.md` for the user-authorized attended-limit baseline
- `plan/2026-09-02-console-chassis-layout-and-range/plan.md`
- `plan/log.md`

## Read-only files and directories

- ESP32 runtime/service source except the declared factory validation ceiling;
  protocol semantics remain read-only
- Credentials, endpoint addresses, CAN parameters, and all other local config
- MaixCam, arm, TCP232, raw resources, and the primary worktree user settings

## Shared Dependencies

- Manual command units remain mm/s and mrad/s
- Existing chassis core absolute bounds remain 600 mm/s and 800 mrad/s
- Existing release-to-STOP, 500 ms hold, 2 s lease, and link-loss disable behavior
- Current deployed device remains limited to 50 mm/s and 100 mrad/s until a
  separately gated device-config deployment

## Risk and safety door

- Risk: The proposed attended ceilings are 200 mm/s linear and 400 mrad/s
  angular. This is still below core limits but materially above the current
  device gate. The default selected values remain 80 and 240.
- Hardware: None during L1 implementation. A later ESP32 config upload/reset is
  L3 because it changes real-motion limits.
- User operations: None for L1.
- Backup and recovery: Git for UI/templates; fresh device_config readback before
  any later upload, with COM7 recovery.
- Motion gate: No motion in this goal's L1 phase. Before deployment and testing,
  reconfirm physical emergency stop, clear/restrained chassis, safe arm, selected
  speed/direction, release-to-stop, and link-loss response.

## Expected work

1. Increase committed/local manual ceilings to 200 mm/s and 400 mrad/s while
   retaining startup selections of 80 and 240.
2. Replace the always-visible Advanced group with a real collapsed section.
3. Shorten routine labels and status text; keep only connection, start/end,
   direction, STOP, and two sliders visible in the normal path.
4. Add/update UI binding tests and operator documentation.
5. Run L1 validation and restart the visible console. Do not deploy device speed
   limits in the L1 phase.
6. After the user confirms L3 deployment, update the factory validation ceiling
   to the unchanged chassis-core absolute bounds (600/800), test it, then deploy
   the factory and 200/400 local configuration together.

## Validation

- Console unit tests and offscreen UI smoke
- Full ESP32 tests to confirm no service behavior changed
- Workspace validator and Python compilation
- `git diff --check`
- `git status --short --branch`

## Actual results

- L1 implementation completed. The normal chassis surface now shows compact
  Link/Owner/Drive status, Connect/Start/End, the direction pad, STOP, two short
  speed labels/sliders, and a compact command vector.
- Raw Acquire/Enable/Disable/Release/manual-unlock controls are placed in a
  genuinely hidden Advanced container with an explicit expand toggle.
- The committed examples and ignored local console config now use 200 mm/s and
  400 mrad/s ceilings. Initial slider selections remain 80 and 240.
- The operator reconfirmed the immediate L3 deployment gate for the 200/400 limit
  change. A fresh ignored backup of `device_config.py` was taken over COM7.
- The first config-only restart correctly exposed a stale factory validation
  ceiling (100/200), so TCP 8765 did not start. No application connection or
  motion command was possible. The device remained recoverable through COM7.
- Scope was expanded to align factory configuration validation with the unchanged
  chassis-core absolute bounds (600/800). The actual configured device gate remains
  200/400. Tests now accept 200/400 and reject 601/801.
- Fresh factory/config backups were taken. Both files were uploaded, read back,
  and matched their local SHA-256 hashes before reset.
- Post-reset non-motion validation returned `WELCOME`, `PONG`, and
  `STATE=ready/disabled`, with no lease and no error. No Acquire, Enable, velocity,
  or robot-arm command was sent.
- Final L1 passed: 204 tests (43 console, 57 ESP32, 28 protocol, 44 MaixCam,
  23 development, 9 robot arm), offscreen smoke, compilation, workspace validation,
  and `git diff --check`.
- The prior UI was stopped. The revised visible UI started as PID 17816 and was
  brought to the foreground.

## Outstanding matters

- Real-speed observation remains an operator action; this goal did not send motion.

## Experience signal (for manual review)


## Intent to submit

```text
refactor(console): simplify chassis panel and widen tuning range
```
