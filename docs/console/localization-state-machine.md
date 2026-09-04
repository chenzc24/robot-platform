# Localization lock state machine

## Purpose and boundary

The PC runtime now owns a fail-closed localization lock between chassis motion
and future coordinate-based tasks. It does not move either device. Its job is to
invalidate stale geometry, wait after a logical chassis stop, collect several
accepted AprilTag board poses, freeze one transform generation, and lend that
immutable generation to a later task executor.

The existing YOLO/manual arm route remains independent. Only a future
coordinate-based executor should call the localized-task interface.

## Frame convention

`T_A_from_B` maps coordinates expressed in frame B into frame A. The locked
board-to-base result is:

```text
T_base_from_board = T_base_from_camera * T_camera_from_board
p_base            = T_base_from_board * p_board
```

`T_base_from_camera` is a measured rigid extrinsic because the GC4653 and arm
base are fixed to the same chassis. `T_camera_from_board` comes from the stable
AprilTag observations after each chassis move. `T_tool0_from_pen` is the fixed
Tool0-to-pen geometry used later with the arm's returned `GetPose(0,0)` sample.
Arm feedback is deliberately not sampled while the board transform is being
locked: a task executor must obtain a fresh Tool0 pose when it actually needs
the current pen pose.

All translations are millimetres and rotations are right-handed 3 x 3 matrices.
The tracked [geometry example](../../config/robot-geometry.example.json) contains
identity placeholders and `production_ready: false`; it cannot produce a lock.
Copy it to ignored `config/robot-geometry.local.json`, replace both matrices with
measured values, and mark it ready only after physical verification.

## States

```text
disabled / blocked
        |
     invalid <-- disconnect, disabled chassis, fault or unknown state
        |
      moving <-- any nonzero PC motion intent invalidates the old generation
        |
     settling <-- ESP32 reports enabled_stopped; timer is still running
        |
    collecting <-- accepted, ready AprilTag poses enter a bounded window
        |
      locked <-- enough samples are mutually stable; generation increments
```

The controller report `enabled_stopped` is logical state, not measured wheel or
IMU velocity. The settling interval reduces risk from residual vibration but is
not proof of physical standstill. A motion-producing system still needs the
planned physical stop/interlock acceptance.

Rejected or intermittent vision frames do not erase good samples already in
the current bounded window. A changed camera calibration ID, board layout ID or
board frame clears that window. A lock requires at least `min_valid_samples`, at
least `min_visible_tags` in every accepted sample, and translation/rotation
spread within the configured limits. Losing sight of the tags after a lock does
not invalidate it because the fixed chassis/base/camera assembly has not moved.
Any possible chassis motion does invalidate it.

## Configuration and observable state

Console schema 5 adds `localization`:

```json
{
  "enabled": false,
  "geometry_path": "config/robot-geometry.local.json",
  "settle_time_ms": 2000,
  "sample_window_ms": 3000,
  "min_valid_samples": 8,
  "min_visible_tags": 2,
  "max_translation_spread_mm": 2.0,
  "max_rotation_spread_deg": 1.0
}
```

Localization also requires enabled, complete AprilTag vision. Missing or
unready geometry produces `blocked`, not a best-effort transform. `GET
/api/state` publishes `localization.state`, reason, sample count, validity,
generation, frozen context, quality summary, and active/last task lifecycle.
`POST /api/localization/relocalize` restarts settling only while the chassis is
confirmed `enabled_stopped` and no localized task is active.

Automatic state changes write concise `Localization` events to the existing
sanitized console journal and text log. They record state, reason and generation,
not matrices or device addresses; accepted frames do not generate per-frame log
noise.

## Future task interface

`WebConsoleRuntime` exposes three intentionally transport-neutral calls:

```python
context = runtime.begin_localized_task("draw-42", expected_generation=7)
runtime.finish_localized_task("draw-42", "DONE", "complete")

# Read-only use without reserving a task:
context = runtime.localized_task_context(expected_generation=7)
```

The returned context is a deep copy containing the generation, frame names,
geometry ID, forward/inverse board transforms, Tool0/pen transforms and source
quality evidence. Supplying the observed generation prevents a queued task from
silently switching to a newer coordinate solution. Only one localized task may
be active. Chassis motion or lost chassis state marks an active task `UNKNOWN`
and removes its context; callers must stop issuing later task commands.

There is intentionally no generic HTTP “execute task” endpoint yet. The later
executor must own command sequencing, fresh arm feedback, workspace checks,
terminal-result handling and the chassis-stopped/arm-safe interlocks rather than
smuggling those responsibilities into localization.

## Validation boundary

L1 tests cover transform validation and composition, stable-window fusion,
source changes, generation checks, task lifecycle, runtime integration and
motion-intent invalidation. They do not validate the two physical extrinsics,
camera intrinsics, AprilTag print dimensions, actual chassis standstill, arm
orientation conventions, Tool0 feedback or drawing accuracy.
