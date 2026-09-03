# Add Robot-Arm Measured Feedback

- Status: `complete`
- Responsible: `agent`
- Highest validation level: `L1`; no device connection or motion

## Objective

Add the smallest end-to-end data path for measured robot-arm state:
`GetAngle/GetPose` on the controller, fixed RPA2 state fields, transparent
MaixCam transport, strict PC parsing, localhost state exposure, and a compact
Current display in the web UI. Targets and measurements must remain separate.

## Initial workspace state

```text
## main...origin/main
 M .vscode/settings.json
```

The `.vscode/settings.json` modification is user-owned and remains untouched,
unstaged, and uncommitted. Work proceeds on
`target/arm-measured-feedback`.

## Editable scope

- `src/robot_arm/runtime/` controller API adapter and status service
- `src/maixcam/arm/` only where required to preserve/advertise feedback
- `src/console/status_mapping.py` and web runtime/static UI
- focused robot-arm, MaixCam, and console tests/fixtures
- robot-arm/API/console documentation and goal/log records

## Read-only scope

- ESP32, chassis, CAN, video, TCP232 configuration, network endpoints,
  credentials, controller safety settings, motion limits, tool IO, coordinate
  calibration, planning, raw resource archives, and `.vscode/settings.json`

## Shared contract

The existing RPA2 frame remains unchanged. The fixed `STATE` field payload is
extended in one coordinated source change with:

```text
feedback_valid
feedback_error
joint_deg
pose
pose_user
pose_tool
sample_id
sample_time_ms
```

- A valid sample contains exactly six finite joint values and six finite pose
  values.
- An invalid sample uses the literal `unavailable` for both vectors and retains
  a fixed feedback error code; it does not stop the arm command service.
- `terminal_position_supported` remains `0` until the actual controller return
  shapes and terminal sampling are verified on hardware.
- `arm.status` is the only request used for this goal; no telemetry stream,
  queue, planner, capability negotiation, or tool IO is added.

## Expected implementation

1. Inject `GetAngle` and `GetPose` into the controller adapter and normalize
   supported fixture shapes through one `read_feedback()` function.
2. Sample feedback while serving `STATUS`; return explicit valid/invalid fields
   without changing any motion primitive.
3. Preserve the downstream state through MaixCam and update its advertised
   status shape only as required.
4. Parse and store the measured sample on the PC, expose it through
   `/api/state`, and display compact Current Joint/Current Pose rows separately
   from target inputs.
5. Add deterministic fixtures for valid data, malformed data, read failures,
   stale age, and target/measurement separation.

## Validation

- focused unit tests for controller normalization and RPA2 status
- MaixCam gateway/service contract tests
- PC strict parser and web runtime/API/static UI tests
- all existing `console`, `dev`, `esp32`, `maixcam`, `protocol`, and
  `robot_arm` suites
- Python/JavaScript syntax checks and `git diff --check`

## Residual hardware work

- L2: record the actual Python type and shape returned by `GetAngle()` and
  `GetPose(0, 0)` while stationary.
- L3: after separate confirmation, perform one 2-degree jog and confirm that
  the measured joint changes independently of the command target.

## Actual implementation

- The controller adapter now calls `GetAngle()` and `GetPose(0, 0)` only while
  serving `STATUS`, normalizes documented vectors and common return wrappers,
  and emits one fixed measured-state payload.
- Failed or malformed feedback is encoded as `feedback_valid=0`, a fixed error
  code, and `unavailable` vectors. It does not change the service motion state.
- MaixCam required no runtime change: a focused test proves that it carries the
  complete downstream `STATE` payload without alteration.
- The PC parser validates exact fields, finite six-value vectors, frame indices,
  sample sequence, timestamp, and valid/error consistency.
- The localhost runtime retains the last valid sample, computes age only from
  the PC receipt clock, and never substitutes an arm target for measurement.
- The web arm panel now includes a compact `CURRENT` box for measured joints,
  measured pose, sample identity/age, and User/Tool frame identity.

## Actual validation

- 243 L1 tests passed: console 63, development 25, ESP32 55, MaixCam 54,
  protocol 28, and robot arm 18.
- 57 affected Python files compiled from source; `app.js` passed `node --check`.
- The DobotStudio two-file YOLO builder completed. Its generated `main.py`
  contains `GetAngle`, `GetPose`, `read_feedback`, and `feedback_valid`, and
  compiles successfully.
- Live localhost browser inspection at 1280 x 720 showed both six-value Current
  rows without clipping the J1-J6 jog controls. The offline state was explicit.
- `git diff --check` passed.
- `validate_workspace.py` remains red only for pre-existing non-ASCII text in
  `src/console/ui/views.py` lines 471 and 487; that legacy Qt file is outside
  this goal and was not modified.
- No L2/L3 check, device connection, deployment, controller write, or physical
  motion was performed.

## Scope result

No MaixCam runtime source, ESP32 source, protocol framing, configuration,
endpoint, credential, safety limit, tool IO, or planner code changed. The
user-owned `.vscode/settings.json` edit remains untouched and unstaged.

## Intent to submit

```text
feat(arm): add measured joint and pose feedback
```
