# Publish the staged-stroke MaixCam gateway

- Status: blocked (MaixCam vendor launcher holds UART0 in uninterruptible sleep)
- Responsible: joint
- Highest validation level: L2

## Objective

Publish the committed MaixCam half of staged stroke protocol `69ecd3a` to the
configured MaixCam release location. Do not deploy the controller project, do
not arm drawing, and do not issue any arm or chassis motion command.

## Audit and ownership

- `main` is synchronized with `origin/main` at `69ecd3a`.
- `.vscode/settings.json` is an unrelated user change and remains read-only.
- `plan/2026-09-09-localized-approach-micro-adjust/` is another active goal;
  its source, simulator and `plan/log.md` scope remain read-only here.

## Editable scope

- this plan, including factual deployment results
- `src/maixcam/arm/run_arm_command_service.sh`, limited to a device-observed,
  non-motion replacement for the hanging BusyBox `pidof launcher_daemon`
  lookup
- the configured MaixCam release directory only, after read-only identity,
  connection, version and recoverability checks

## Read-only scope and dependencies

- all version-controlled runtime source, local configuration, ESP32, controller
  project, drawing job, raw-resource archives and the other active goal
- the existing MaixCam release and launcher, except for a release-directory
  upload and explicitly authorized restart after backup/readback

The release depends on the current PC protocol source, the existing SSH target,
and the user-provided authorization to deploy MaixCam. The older controller
project deliberately remains incompatible until a separate LAN2 deployment.

## Validation and recovery

- read the configured target identity, SSH reachability, active process and
  release path without printing credentials
- preserve the current release identity and retrieve the existing gateway files
  or hashes before overwrite
- upload only the MaixCam arm gateway/protocol files to a new versioned release
  directory; do not overwrite the current release in place
- switch/restart only after confirming the uploaded hashes and retain the old
  release path as rollback
- perform a non-motion L2 service/port or protocol check; reject any action
  that would arm or move the robot

## Completion boundary

Record actual commands, hashes, remote state, recovery path and validation in
this plan. `plan/log.md` is intentionally not modified because the other active
goal owns it. Controller deployment and all post-change motion remain separate
explicitly safety-gated work.

## Actual deployment facts

- Read-only SSH identity check reached `maixcam-6c7d` and verified the existing
  arm gateway process, old release hashes and local device-specific arm
  configuration without printing credentials.
- Uploaded and hash-checked staged-stroke gateway files in independent release
  directories `69ecd3a-arm`, `69ecd3a-arm-r1` and `69ecd3a-arm-r2`; the original
  `/root/robot-platform/arm` directory was never overwritten. The local config
  was copied only on-device into each release directory.
- The device BusyBox `pidof launcher_daemon` hung during guarded launch. Source
  now identifies the known supervisor by `/proc/*/exe`, with a longer graceful
  UART-release wait. The revised script passed supervisor verification but the
  verified vendor launcher PID 2216 did not release `/dev/ttyS0` after TERM.
- The user explicitly authorized one force path. It was guarded by explicit
  `FORCE_LAUNCHER_KILL=1`, revalidated the owner executable, and attempted
  SIGKILL only after the normal wait. UART0 remained held. A final read-only
  check found PID 2216 at `/maixapp/apps/launcher/launcher`, state
  `D (disk sleep)`, wchan `do_page_fault`; it cannot be safely killed by this
  host process.
- The user then explicitly authorized a MaixCam reboot. SSH confirmed the
  reboot completed and the device again identified as `maixcam-6c7d`. A normal
  launch of `69ecd3a-arm-r3` again reported `uart_release_failed`; the
  previously authorized guarded force path was also attempted. The replacement
  vendor launcher (again PID 2216) remained the sole UART0 owner and was again
  observed in `D (disk sleep)`, with parent PID 296.
- No new arm gateway reached port 8780; non-motion PING/STATUS was refused.
  No arm/chassis motion, controller deployment, configuration change or
  firmware write occurred. The safe state is no active arm gateway while the
  launcher holds UART0.

## Blocker and recovery

The authorized reboot did not clear the vendor-launcher failure. On-site
vendor-launcher recovery or diagnosis is required before retry; do not repeat
the deployment or reboot automatically. Afterwards, verify launcher ownership,
start only the newest guarded release, then perform PING/STATUS before any
controller or motion work.
