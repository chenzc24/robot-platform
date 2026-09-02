# Dobot Robot-Arm API Reference for This Project

- Scope: Magician E6 controller-resident project used by the MaixCam arm route
- Purpose: record only APIs that may support motion, measured feedback, tool IO,
  configuration, and diagnostics in this repository
- Source basis: user-provided Dobot instruction excerpts and the read-only
  controller Python export tables recovered from the course runtime
- Language note: the instruction examples use Lua-like table syntax. The
  deployed project is Python and receives wrappers around `pluginPy`; exact
  Python return shapes must be captured in a non-motion L2 probe before they
  become a strict wire contract.

## 1. Project priority

| Priority | APIs | Intended use |
|---|---|---|
| P0 | `GetPose`, `GetAngle` | Real measured Cartesian pose and six-joint feedback in `arm.status` and motion completion |
| P0 | `CheckMovJ`, `CheckMovL` | Preflight absolute paths before `MovJ` or `MovL` |
| P0 | `VelJ`, `AccJ`, `VelL`, `AccL`, `CP` | Explicit per-project motion behavior and zero-blend debug moves |
| P1 | `ToolDI`, `GetToolDO`, `ToolAI` | Read gripper, sensor, and tool IO state |
| P1 | `ToolDO`, `SetToolPower` | Explicit tool actuation and tool-power recovery commands |
| P1 | `SetToolMode`, `SetTool485` | One-time tool interface configuration |
| P2 | `User`, `Tool`, `CalcUser`, `CalcTool` | Coordinate-frame selection and calibration workflow |
| Maintenance only | `SetPayload`, `SetUser`, `SetTool`, safety setters | Commissioning and controller configuration, not routine UI controls |
| Not currently required | `GetABZ` | External ABZ encoder input; it is not the six-joint position source |

## 2. Measured state

### `GetPose(user_index, tool_index)`

Returns the robot's current Cartesian pose:

```text
pose = [x, y, z, rx, ry, rz]
```

- `user_index` is optional and selects the user coordinate frame.
- `tool_index` is optional and selects the tool coordinate frame.
- Without arguments, the current global User and Tool selections apply.
- UI and protocol state must always include the User and Tool indices alongside
  the pose. A pose without its coordinate-frame identity is ambiguous.
- When blending is disabled (`cp=0` or `r=0`), a sample taken between completed
  moves can accurately represent the reached target. With blending enabled, a
  sample may lie on the transition curve.

Project use:

```python
raw_pose = GetPose(0, 0)
```

This call is confirmed in the Python export table. The displayed container and
numeric types remain L2 evidence to collect.

### `GetAngle()`

Returns current joint angles:

```text
joint = [j1, j2, j3, j4, j5, j6]
```

Project use:

```python
raw_joint = GetAngle()
```

This call is confirmed in the Python export table. As with `GetPose`, the
Python result must be normalized only after its actual shape is recorded.

### `GetABZ()`

Returns the current position of a configured external ABZ encoder. It must not
be presented as robot-joint feedback. Add it only if the final tool or an
external axis actually uses an ABZ input.

## 3. Required feedback contract

The controller service should normalize `GetPose` and `GetAngle` into six
finite numbers each and publish this measured sample:

```text
joint_deg=j1,j2,j3,j4,j5,j6
pose=x,y,z,rx,ry,rz
pose_user=0
pose_tool=0
sample_time_ms=<controller monotonic time>
terminal_position_supported=1
```

The complete route is:

```text
GetPose / GetAngle
  -> robot-arm resident service
  -> LAN1 / TCP232 / UART
  -> MaixCam arm gateway
  -> Wi-Fi NDJSON
  -> computer runtime
  -> localhost API
  -> measured-position fields in the web UI
```

Required semantics:

1. `arm.status` returns the latest measured joint and pose sample.
2. A successful motion obtains a fresh sample before `DONE` and returns it as
   the terminal measurement.
3. Command targets and measured values remain separate fields.
4. Missing, malformed, stale, or non-finite feedback is displayed as
   unavailable; a target value is never substituted.
5. The current 500 ms computer status cycle is a suitable initial idle polling
   interval.
6. Continuous in-motion feedback is not yet guaranteed. If `MovJ` or `MovL`
   blocks the controller's single service loop, only idle and terminal samples
   are available until controller concurrency is verified.

## 4. Motion parameters

### `CP(R)`

- Sets continuous-path smoothing for the current project run.
- Range: `0..100` percent.
- `0` disables smoothing and is the required default for discrete manual debug
  moves and terminal-position validation.

### `VelJ(R)` and `AccJ(R)`

- Set the default joint-motion velocity and acceleration ratios.
- Range: `1..100` percent.
- Apply to joint motion including `MovJ` and `RelJointMovJ`.
- Per-command `v` and `a` options remain preferable in the gateway because
  they keep each request self-contained.

### `VelL(R)` and `AccL(R)`

- Set default linear/arc velocity and acceleration ratios.
- Range: `1..100` percent.
- Apply to `MovL`, arc motion, and related relative linear commands.

### `SpeedFactor(ratio)`

- Sets the global project speed ratio.
- Range: `1..100` percent.
- It is stateful for the current project run and multiplies lower-level motion
  settings. If exposed later, its current value must also be reported so the
  UI does not misrepresent effective speed.

### `SetPayload(...)`

Supported forms:

```text
SetPayload(payload_kg, [x, y, z])
SetPayload(preset_name)
```

The direct form specifies payload mass and offset in millimetres. The named
form uses a controller preset. Payload affects motion safety and must remain a
deployment/commissioning setting rather than a routine web-console action.

## 5. Coordinate systems

### Runtime selection

```text
User(user_index)
Tool(tool_index)
```

These choose global coordinate frames for the current project run. An explicit
frame on a motion or `GetPose` request should take precedence over globals.
Selecting an empty or nonexistent frame can stop the controller project.

### Calculation

```text
CalcUser(index, matrix_direction, [x, y, z, rx, ry, rz])
CalcTool(index, matrix_direction, [x, y, z, rx, ry, rz])
```

- Index range documented as `0..50`.
- `matrix_direction=1` applies the offset in the base/flange frame.
- `matrix_direction=0` applies it in the selected frame itself.
- These functions calculate and return a frame; they do not need to persist it.

### Mutation

```text
SetUser(index, frame, persist=0)
SetTool(index, frame, persist=0)
```

`persist=1` changes controller-global configuration beyond the current project
run. These commands are outside the runtime UI and require explicit deployment
authorization and a recovery record.

## 6. Path preflight

### `CheckMovJ(P, options)`

Checks the complete joint-motion trajectory from the current state to `P`.
Relevant options include User, Tool, acceleration `a`, velocity `v`, and blend
`cp`. The current service already requires a result of `0` before `MovJ`.

### `CheckMovL(P, options)`

Checks the complete linear/arc trajectory. Relevant options include User,
Tool, `a`, `v` or absolute `speed`, and `cp` or radius `r`. The current service
already requires a result of `0` before `MovL`.

Documented result codes:

| Code | Meaning |
|---:|---|
| 0 | Path accepted |
| 16 | Target near shoulder singularity |
| 17 | Target has no inverse-kinematics solution |
| 18 | Target inverse solution exceeds limits |
| 22 | Arm-configuration transition error |
| 26 | Target near wrist singularity |
| 27 | Target near elbow singularity |
| 29 | Invalid speed parameter |
| 30 | Full inverse-kinematics solution failed |
| 32 | Shoulder singularity exists on trajectory |
| 33 | An unreachable point exists on trajectory |
| 34 | A joint-limit violation exists on trajectory |
| 35 | Wrist singularity exists on trajectory |
| 36 | Axis singularity exists on trajectory |
| 37 | Joint discontinuity exists on trajectory |

Any nonzero result is a local controller rejection, not a transport failure,
and must not be automatically retried.

## 7. Tool IO

### Inputs and output feedback

```text
ToolDI(index)       -> ON or OFF
GetToolDO(index)    -> ON or OFF
ToolAI(index)       -> analog value
```

- `ToolDI` reads a tool digital input.
- `GetToolDO` reads the current tool digital-output state.
- `ToolAI` reads a tool analog input after the multiplexed terminal is placed
  in analog-input mode.
- Hardware without the corresponding analog interface may return no useful
  value; capability must be discovered during commissioning.

These are candidates for read-only `arm.status.tool_io` fields. Each sample
must retain the port index and collection time.

### Digital output

```text
ToolDO(index, ON | OFF)
```

This is a queued state-changing command. It is confirmed in the controller's
all-thread export table. It must use explicit port/value parameters, report the
result through `GetToolDO`, and must not be automatically retried after an
unknown outcome.

### Multiplexed terminal mode

```text
SetToolMode(mode, type, identify=1)
GetToolMode(identify=1) -> mode, type
```

Documented `mode` values:

- `1`: RS485 mode; `type` is ignored.
- `2`: analog-input mode.

For analog mode, each decimal digit in `type` selects one channel:

- `0`: 0-10 V input;
- `1`: current input;
- `2`: 0-5 V input.

`identify` chooses connector 1 or 2 on models with multiple tool connectors.
`SetToolMode` is confirmed in the Python export table. `GetToolMode` appears in
the supplied instruction documentation but was not found in the inspected
Python export snapshot, so it remains unavailable until an L2 capability probe
confirms it.

### Tool power

```text
SetToolPower(0 | 1)
```

This turns tool power off or on and is commonly used to reinitialize a gripper.
Turning power off also invalidates tool digital outputs. Repeated calls should
be separated by at least the documented 4 ms; a practical power-cycle command
should use a substantially clearer device-specific delay and report both
steps. This is an explicit recovery action, not an automatic fault response.

### Tool RS485 format

```text
SetTool485(baud, parity="N", stopbit=1, identify=1)
```

- `parity`: `O`, `E`, or `N`.
- `stopbit`: `0.5`, `1`, `1.5`, or `2`.
- `identify`: connector 1 or 2 where supported.

This is commissioning configuration. It should be stored in a reviewed local
deployment profile and not exposed as a normal runtime control.

## 8. Controller safety setters

```text
SetSafeWallEnable(index, enabled)   # index 1..8
SetWorkZoneEnable(index, enabled)   # index 1..6
SetCollisionLevel(level)            # 0..5
SetBackDistance(distance_mm)        # 0..50 mm
```

These values affect controller safety behavior for the current project run.
They must not become ordinary UI toggles or be changed merely to make a test
pass. Their current configured values, device support, and recovery procedure
must be confirmed before any deployment change.

## 9. Python export evidence

The inspected controller bundle confirms Python wrappers for:

- `GetPose`, `GetAngle`, `GetABZ`, and `SpeedFactor`;
- `CP`, `VelJ`, `AccJ`, `VelL`, `AccL`, `User`, `Tool`, `SetPayload`,
  `SetUser`, `CalcUser`, `SetTool`, and `CalcTool`;
- `CheckMovJ` and `CheckMovL` on the main-thread export list;
- `ToolDI`, `ToolAI`, `GetToolDO`, `SetToolMode`, `SetToolPower`, and
  `SetTool485`; and
- `ToolDO` on the all-thread export list.

This confirms names and call forwarding, not return container shapes or support
on every controller hardware revision.

## 10. Required non-motion verification

Before implementing strict feedback parsing, run one attended L2 probe through
the controller project without a motion command:

1. Call `GetAngle()` once and record only its Python type, shape, and finite
   numeric values.
2. Call `GetPose(0, 0)` once and record the same evidence plus User/Tool frame.
3. Repeat both calls while stationary to confirm stable parsing.
4. Query only the tool inputs physically present on this E6 configuration.
5. Probe `GetToolMode()` separately; absence must not stop the normal arm
   service.

Only after these results are known should `terminal_position_supported` change
from `0` to `1` in the shared arm status contract.
