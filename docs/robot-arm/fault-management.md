# Arm fault diagnosis and recovery foundation

Status: local L1 implementation; not deployed or validated on a moving robot.

This is a foundation for future avoidance, not an automatic singularity planner.
It keeps capability queries, measured state, path checks, execution, and fault
recovery distinct. Curve planning remains a future computer-side responsibility.

## Available on the current controller project

| Operation | Current implementation |
|---|---|
| Query fault capabilities | Available after coordinated deployment |
| Preserve native path-check result | CheckMovJ / CheckMovL numeric code, API name, bounded raw evidence |
| Preflight XYZ jog | GetPose in the requested User/Tool frame, translate XYZ, CheckMovL, then RelMovLUser |
| Query latest service error | Available; separate from actual controller alarms |
| Query actual controller alarms | Unsupported in the current project adapter |
| Clear actual controller alarms | Unsupported in the current project adapter |
| Verify/recover a latched service fault | Unsupported until a verified controller-state adapter is connected |

The inspected E6 4.6.0.3 package exports CheckMovJ, CheckMovL, GetPose, GetAngle,
CheckOddMovJ/L/C and the motion primitives. Its normal Python project export
tables do not export GetErrorID, RobotMode or ClearError. A ClearError symbol
inside pluginPy.so is not evidence of a supported script API. Do not import an
undocumented binary function or create an extra native TCP connection in main.py.
Native TCP SDK availability does not imply controller-Python availability.

No LAN1 port, TCP232 mode, LAN2 role, controller mode, safety setting, tool/user
calibration, taught point or network responsibility changes in this release.

## XYZ and absolute-path preflight

1. For XYZ, read GetPose(user, tool) immediately before checking. Do not use a
   cached UI pose or assume the base frame equals the requested user frame.
2. Add dx/dy/dz to that pose's XYZ. Keep its orientation unchanged. Validate
   finite numbers, including the result of the addition.
3. Call CheckMovL with that target, the same User/Tool, speed and acceleration,
   and zero blend radius.
4. Only a verified zero check result permits the existing RelMovLUser call.
   This remains a translation in the user frame, not a tool-frame translation.

Absolute MovL and MovJ likewise retain their preflight checks. Nonzero results
preserve the exact numeric code, including unfamiliar codes. Invalid, Boolean,
ambiguous compound, or missing check results are rejected as unverified, not
converted to success or a fabricated vendor -1. Currently accepted shapes are
an integer or a singleton integer tuple; confirm the actual device return shape
in L2 before deploying for motion.

Only the reviewed single runtime owner may command the arm. A successful check
is not an environment collision certificate, continuous singularity margin,
execution guarantee or substitute for controller safety. A singular posture is
not removed by clearing its alarm. Repeating the same XYZ request is not a
recovery strategy; any escape movement is a separate attended L3 action.

## Fault evidence and history

Fault-v1 fields are error_code, retryable, category, vendor_code, vendor_api,
raw_hex, raw_truncated, sample_time_ms and fault_id.

- Categories distinguish preflight, controller execution, recovery, capability,
  and service errors. A vendor code is meaningful only with its source API and
  firmware documentation; no code is inferred from an English exception string.
- raw_hex is the UTF-8 encoding of a compact JSON representation of the native
  return value, or exception text, capped at 64 bytes. It is not a full packet
  capture. raw_truncated explicitly marks a prefix; never treat it as complete
  evidence. Integer codes remain separately preserved. It safely transports
  Chinese text and framing delimiters without injecting wire fields or HTML.
- sample_time_ms is controller-local monotonic time where supported (wall-clock
  fallback otherwise), not UTC or a clock synchronized with the PC. The PC adds
  its own timezone-aware received_at and computes query age using its own clock.
  Diagnostic snapshots become stale after five seconds or disconnection.
- The service keeps its latest 16 fault records in RAM. The initial query returns
  the latest record, not a complete historical export. Restart loses that RAM
  history. A successful action does not erase prior records.
- The PC retains evidence in fault cards and its bounded event history, and
  writes ARM_EVIDENCE records when the existing event journal is configured.
  Journal write failures remain visible. Archive that log for long-term analysis.
- ACK in the UI only marks evidence as seen. It does not clear controller alarms,
  reset the service, enable anything, or remove the historical event.

The controller now writes ACK/RUNNING before the synchronous vendor call. These
are service lifecycle messages, not proof of physical motion. A native pause
can still block main.py: this is not a concurrent alarm/stop channel. Physical
emergency stop and DobotStudio maintenance remain necessary. DONE still means
the sequential controller call returned, not measured terminal pose.

## Explicit clear and recovery contracts

ControllerFaultAccess is an injectable, offline-tested boundary. Production
constructs it with no callbacks. A future approved vendor adapter must prove:

- read() performs a fresh controller query and returns alarm_codes (integer
  list), stationary, queue_empty and emergency_stop (strict Boolean values).
  It must not claim queue_empty from a mere TCP acknowledgement or cached mode.
- clear() returns a verified integer vendor request result. Zero is only command
  success, not proof that alarms disappeared.
- No callback switches control modes, enables, releases brakes, resumes, changes
  safety settings, or replays a pending command as a side effect.

Clear requires an explicit confirmation, supported read/clear capability, and
a verified stationary controller with an empty queue and no emergency stop.
It snapshots before, invokes clear once, then verifies state and alarms again.
Failures or unresolved alarms never return a confirmed success. Successful
responses carry before/after alarm evidence, sample times and the clear result.
This strict gate intentionally does not clear a paused job's alarms and then
silently resume it. Handling such a job is a separate maintenance procedure.

Service recovery is a separate explicit operation. It verifies no controller
alarms, stationary state, an empty queue and no emergency stop, then resets only
the service latch. It does not call ClearError, enable, resume, replay, reset
sequence deduplication, or delete fault history. An old UNKNOWN motion event
remains UNKNOWN even after recovery; new work is a separate request.

State-changing partial writes, response loss and timeouts are UNKNOWN and are
never retried automatically. Do not click repeatedly to resolve uncertainty.
Read actual state and inspect the robot through the approved maintenance path.

## Computer API and console

Python methods on the existing MaixCamArmClient:

```python
client.capabilities()
client.faults(scope="service")
client.faults(scope="controller")  # capability-gated; unavailable today
# Explicit state-changing requests, not startup/automatic recovery actions:
client.clear_errors(confirm=True)
client.recover_service(confirm=True)
```

The last two are contracts, not instructions to run them now. The default
controller adapter rejects them without performing a vendor call.

Web console Diagnostics provides READ ARM FAULTS, CLEAR CONTROLLER ALARMS and
RECOVER SERVICE separately. Recovery buttons require supported capabilities,
an idle UI task, and an explicit confirmation. The backend re-queries capability
and the controller enforces its own gate; browser state is not authorization.

- POST /api/arm/diagnostics: queries capability and service evidence; queries
  controller alarms only if advertised. No motion permission is required.
- POST /api/arm/recovery: action clear_errors or recover_service, confirm true.
  No auto-enable/resume endpoint is added. Unsupported remains an error, not DONE.

## Deployment, validation and remaining gates

This extension retains RPA2/512-byte framing, but changes ERROR payloads and adds
commands. Do not deploy it to just the controller while an old gateway is active.
Use a stopped-task release: export/retain the known-good controller project,
build a new two-file project, deploy matching controller/protocol and MaixCam
sources, then the PC. New gateways accept legacy two-field errors, but old
gateways do not understand the new fault fields. No automatic protocol upgrade
is performed. ESP32 is unaffected and does not need deployment for this change.

L2 must verify actual check-return shapes, matching User/Tool pose conventions,
CAPS and service fault responses, raw timestamps and frame limits without motion.
Retain controller-clear capabilities as false until a separately reviewed,
supported path and its state-query semantics are proven. Clear/alarm reset can
change hardware safety state and needs explicit device-operation authorization.
L3 then tests a bounded safe XYZ movement and a nonmoving rejected preflight
with an on-site operator and physical emergency stop. No L2/L3/L4 was run here.

Reference: [official TCP SDK](https://github.com/Dobot-Arm/TCP-IP-Python-V4/tree/55ec1ec82201aaf2e6d54aa47b6272bbaa14c815),
[controller check documentation](https://github.com/Dobot-Arm/TCP-IP-Python-V4/blob/55ec1ec82201aaf2e6d54aa47b6272bbaa14c815/assets/手臂二开md文档/手臂二开md文档段落三.md),
and the locally inspected 4.6.0.3 Python export tables (raw resources remain
read-only and untracked). Reusing the native SDK requires a separate integration
decision, not changing the existing 5200 service into a native Dashboard socket.
