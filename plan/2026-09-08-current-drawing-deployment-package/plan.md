# Current drawing deployment package

- Status: `completed`
- Responsible: `agent`
- Highest validation level: `L1`

## Objective

Freeze current clean `main` commit `97253c9` into one local, hash-verifiable
deployment directory containing the ESP32 runtime files, MaixCam arm/video
release files, and a newly generated YOLO-mode DobotStudio project compatible
with the current `blend_pct`/`cp=100` drawing chain.

## Initial state of the workspace

```text
## main...origin/main
```

The previous candidate freezes obsolete commit `301320c` and predates the
current MaixCam/controller blend protocol. Existing ignored build outputs and
all deployed device files are preserved.

## Modifyable File

- new ignored output under `build/drawing-97253c9/`
- `docs/deployment/2026-09-08-current-drawing-package.md`
- `docs/deployment/2026-09-08-current-drawing-package.json`
- `docs/deployment/README.md`
- `plan/2026-09-08-current-drawing-deployment-package/plan.md`
- append-only `plan/log.md`

## Read-only files and directories

- all files under `protocol/`, `src/`, `tools/` and `config/`
- all older `build/` outputs
- local secret/configuration files and device backups
- ESP32, MaixCam, TCP232 and robot-arm device files/state
- raw-resource archives `ESP32/`, `Camera/`, and `Robot Arm_Claws/`

## Shared Dependencies

- `protocol/chassis_tcp_v3.py`, ESP32 production app modules and preserved
  device-local `device_config.py`/`secrets.py`
- MaixCam arm/video sources plus flat copies of shared protocol modules
- `tools/robot_arm/build_dobotstudio_project.py --yolo`
- current PC runner and local configuration gates

## Risk and safety door

- Risk: packaging mistakes can cause incompatible device deployment tomorrow;
  package content must exclude secrets and be hash-verifiable.
- Hardware: none.
- User operations: none in this goal.
- Backup and recovery: generated output is new and ignored; existing build
  outputs and device files are untouched. Tomorrow's deployment must back up
  every target before replacement.
- Motion gate: no device connection or motion. Deployment begins with L2 in a
  stopped/default-deny state; L3/L4 requires a fresh attended safety gate.

## Expected work

1. Assemble exact ESP32 and MaixCam layouts without local configuration or
   secrets, and generate a fresh controller project.
2. Generate SHA-256 manifests and deployment instructions identifying every
   preserved local configuration file.
3. Validate package/source hashes, deterministic arm generation, Python/shell
   syntax, JSON structure and applicable tests.

## Validation

- verify every packaged byte against its source or generated expectation
- build the robot-arm project twice and compare all four outputs
- compile packaged Python where the target syntax permits it
- parse every packaged JSON file
- run applicable ESP32, MaixCam, robot-arm and protocol tests
- `git diff --check`
- `git status --short --branch`

L1 validates package completeness and compatibility only. It does not prove
device upload, process ownership, camera/UART availability, physical calibration
or motion.

## Actual results

- Generated ignored directory `build/drawing-97253c9` with 43 files: 41
  manifest payloads plus the copied deployment guide and manifest. Generated
  `build/drawing-97253c9.zip` and the adjacent SHA-256 file.
- The payload contains 14 flat ESP32 runtime files, 8 MaixCam arm files, 7
  MaixCam video files, 4 fresh DobotStudio files, 3 device-config templates and
  5 PC configuration templates. No real local configuration or secret file is
  included.
- Every payload hash matches the committed manifest; every copied runtime/config
  template matches its repository source. The package manifest and guide match
  their committed copies, and all 43 ZIP entries match the directory bytes.
- A second YOLO DobotStudio build matched `main.py`, `var.py`, `prj.json` and
  `point.json` byte-for-byte. The generated controller `main.py` hash is
  `df6149abdda455a429baf641194f410a135bb33350964fd04158d5a9de29a046`.
- Packaged Python and shell syntax and all JSON documents passed. All 385
  repository tests passed: app 13, console 163, development 28, ESP32 76,
  MaixCam 58, protocol 28 and robot arm 19. `git diff --check` passed.
- The final ZIP SHA-256 is
  `6713bb2f11677f604a4dc8f6e308fd3008af11eb43582a041e81df148485ecab`.
- No device connection, upload, import, service action, local configuration
  change or motion occurred.

## Outstanding matters

- Device deployment, readback, L2 handshake, current local configuration review,
  calibration and all L3/L4 motion remain tomorrow's attended work.
- A first validation copy containing compiler-created `__pycache__` was moved to
  ignored `tmp/drawing-97253c9-validation-contaminated`; it is not part of the
  final directory or ZIP.

## Experience signal (for manual review)


## Intent to submit

```text
docs(deploy): freeze current drawing deployment package
```
