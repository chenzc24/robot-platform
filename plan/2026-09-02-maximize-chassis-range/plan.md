# Maximize Chassis Command Range

- Status: `complete (merged to main; device deployment pending)`
- Responsible: `agent`
- Highest validation level: `L1`; real deployment/motion remains pending

## Objective

Expose the full currently defined chassis command envelope through the PC
console and the ESP32 deployment inputs: 600 mm/s resultant planar speed and
800 mrad/s yaw rate. Retain the existing 200 RPM wheel cap and all protocol,
state, stop, disable, and connection-health behavior.

## Initial workspace state

```text
## main...origin/main
 M .vscode/settings.json
```

The `.vscode/settings.json` modification is user-owned, unrelated, and must
remain untouched, unstaged, and uncommitted. Work proceeds on
`target/maximize-chassis-range`.

## Editable scope

- PC console speed-limit defaults, UI ranges, and focused tests
- committed ESP32 L3 configuration template
- ignored `config/console.local.json` and
  `src/esp32/app/device_config.py`, limited to the two requested limits
- active overall, console, and ESP32 limit documentation
- this goal plan and `plan/log.md`

## Read-only scope

- credentials, endpoints, CAN assignments, motor IDs, acceleration/PI/filter
  settings, wheel geometry, `L3_MOTION_PERMITTED`, and health/hold timings
- ESP32 protocol ceiling, chassis kinematics, and MotorBus wheel cap except for
  read-only verification that the requested range is already supported
- MaixCam, robot arm, TCP232, raw resources, and every real device filesystem

## Shared dependencies

- RCP/TCP v3 already accepts each planar component up to 600 mm/s and yaw up
  to 800 mrad/s.
- `SafeMecanumChassis` caps resultant planar speed at 0.60 m/s, yaw at
  0.80 rad/s, and scales combined wheel commands to 200 RPM.
- The PC controller checks resultant `sqrt(vx^2 + vy^2)`, matching the ESP32
  service rather than permitting 600 mm/s independently on both axes.

## Validation

- verify local PC and ESP32 deployment limits match 600/800
- console, ESP32, protocol, and development-tool tests
- Python source validation, offscreen UI smoke, local configuration parsing,
  `git diff --check`, secret/scope review, and final Git status

## Deployment boundary

No device connection, upload, reset, enable, CAN write, or real motion is part
of this goal. Full-range device deployment and motion validation require a
fresh on-site L3 safety confirmation.

## Integration authorization

The user subsequently requested that this validated branch be merged into
`main`. The merge may proceed after confirming the target branch and
`origin/main` have not diverged. This does not authorize device deployment or
motion.

The branch was fast-forwarded into `main` through `dcad8fe` and pushed to
`origin/main` without including the user's local VS Code settings.

## Intent to submit

```text
feat(chassis): expose full command range
```

## Actual result

- Committed PC and ESP32 L3 examples now default to 600 mm/s resultant planar
  speed and 800 mrad/s yaw rate.
- Ignored local PC and ESP32 deployment configurations were migrated to the
  same 600/800 values without changing endpoints, credentials, motion
  permission, health timeout, hold duration, CAN assignments, or motor tuning.
- Hardware and simulator UI sliders expose 10..600 mm/s and 10..800 mrad/s;
  startup selections remain 80 mm/s and 240 mrad/s.
- The RCP/TCP v3 envelope, ESP32 service, chassis kinematics, and 200 RPM wheel
  scaling remain the final layered bounds. A regression test proves 600/800 is
  admitted and a 600/600 planar request is rejected because its resultant
  exceeds 600 mm/s.

## Actual validation

- Protocol: 28 passed plus 6 subtests.
- ESP32: 55 passed plus 2 subtests.
- Console: 49 passed.
- Development tooling: 25 passed.
- Focused full-range regression set: 46 passed.
- Python source validation checked 36 files, offscreen UI smoke passed, local
  PC/ESP32 configuration alignment passed, and `git diff --check` passed.
- No hardware connection, device write, CAN command, or physical motion was
  performed.
