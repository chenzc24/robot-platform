# Preserve four-slot pen rack configuration in drawing plans

- Status: `completed`
- Responsible: `agent`
- Highest validation level: `L1`

## Objective

Extend PR #9's preview-only drawing planner with the four taught pen-slot joint
positions from the supplied controller project. Preserve the controller's 60 mm
normal change/pick depth and 30 mm final-return depth as explicit configuration,
and describe select/change/final-return operations without adding an execution
or device connection path.

## Initial workspace state

The isolated worktree is clean and synchronized:

```text
## target/drawing-job-planner...origin/target/drawing-job-planner
0  0
```

The primary worktree remains dirty with pre-existing user/other-goal changes and
is read-only for this goal.

## Modifiable files

- `config/drawing.example.json`
- `src/console/drawing/config.py`
- `src/console/drawing/planner.py`
- `tests/console/test_drawing_job.py`
- `tests/app/test_drawing_task.py`
- `docs/robot-arm/pc-drawing-task.md`
- `plan/2026-09-08-four-slot-pen-planning/plan.md`
- `plan/log.md` (append only after validation)

## Read-only inputs

- `E:\Downloads\机械臂代码——1代.zip`
- Primary worktree and all device files
- `ESP32/`, `Camera/`, `Robot Arm_Claws/`, `tmp/`
- Existing runtime protocol and MaixCam/robot-arm services

## Shared dependencies

- Supplied `point.json` P1-P4 joint vectors, all recorded with User 0 / Tool 0
- Supplied `main.py` behavior: normal pen pickup/change depth 60 mm, gripper
  values open 60 and closed 1, and final `guiwei` return depth 30 mm
- Existing preview-only safety boundary from PR #9

## Expected work

1. Add an exact four-slot rack schema with six-axis joint vectors and explicit
   change, final-return and gripper parameters.
2. Validate every group mapping against one of P1-P4.
3. Emit configured select/change/final-return plan steps, avoiding a redundant
   change when adjacent color groups share a physical slot.
4. Preserve the delivered five-group behavior by mapping black to the same P3
   pen as pink, while keeping only four physical slots.
5. Update deterministic tests and documentation.

## Safety and validation

- Hardware: none; no connection, deployment, write or motion.
- L1: focused planner/CLI tests, applicable regression partitions as warranted,
  Python source check, JSON parse, device-import scan, `git diff --check`, staged
  scope/secret audit and branch synchronization.
- This confirms only configuration and abstract planning. Taught points,
  collision clearance, gripper widths, descent direction and physical rack
  alignment remain unverified until a separately authorized L3 test.

## Actual results

- Added an exact P1-P4 rack model using the six-axis joint vectors from the
  supplied `point.json`. Configuration validation rejects missing/additional
  slots, malformed vectors, unknown group mappings, invalid depths and invalid
  gripper width ordering.
- Preserved `change_depth_mm=60`, `final_return_depth_mm=30`, gripper open 60
  and closed 1 as explicit example values. The five supplied groups map to four
  slots, with pink and black sharing P3.
- Preview planning now attaches complete joint/relative-Z/gripper recipes to
  pen selection and return steps. Different adjacent slots generate a 60 mm
  return and pickup; groups sharing a slot do not trigger redundant pen motion;
  the final return uses 30 mm and ends at the configured home joints.
- The supplied drawing preview completed with 5 groups, 439 strokes, 3,903
  points, 5,220 drawing-arm commands, 4 physical pen selections and no barrier.
  It remained `preview_only=true` and `production_ready=false`.
- L1 passed 22 app tests, 101 applicable console tests and 3 importer tests
  (126 total). The repository source checker passed 7 files, example JSON
  parsing and `git diff --check` passed. Two existing PySide6 GUI suites remain
  excluded because the shared environment lacks PySide6.
- No hardware, service, endpoint, deployment, device write or motion occurred.

## Residual risk

- The copied P1-P4 joints, User/Tool 0 assumption, rack clearances, Z direction,
  60/30 mm depths and gripper values have not been physically revalidated.
- Pen recipes remain plan data. Runtime admission, feedback checks, failure
  handling and checkpoint-held-pen state belong to the future executor goal.

## Submission intent

```text
feat(console): preserve four-slot pen rack plan
```

## Submission

- Implementation commit: `0511a72`
- Pushed to existing PR #9 targeting `main`; no merge performed.
