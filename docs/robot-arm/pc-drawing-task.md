# PC grouped drawing import and offline planning

The first PC migration stage is deliberately unable to move hardware. It safely
converts the delivered DobotStudio `var.py` literal, validates drawing and local
configuration, and emits an abstract preview plan for later execution work.

It does not import `MaixCamArmClient`, open a socket, initialize a device, expose
an `--execute` option, or run the delivered controller `main.py`.

## Import the delivered project

The importer accepts a ZIP, a Dobot project directory, or one `var.py`:

```powershell
python tools/dev/import_dobot_drawing.py `
  "E:\Downloads\机械臂代码——1代.zip" `
  dataset/dobot-generation-1.json
```

It accepts exactly one source statement of the form `data = <literal>` and uses
`ast.literal_eval`. Imports, calls, expressions, additional assignments and ZIPs
with more than one `var.py` are rejected. Existing output is preserved unless
the operator explicitly supplies `--overwrite`.

The supplied archive produces five groups, 439 strokes and 3,903 points. Its
canonical data hash is:

```text
dd78bd83f4553881b9c9c841b860c61699e16b99b668783b70c5fc7339d13da7
```

The converted file lives under ignored `dataset/` and is not committed.

## Drawing formats

The loader accepts:

- the delivered grouped structure, with `groups[].name` and
  `groups[].strokes`; or
- a flat StrokeReview version-1.0 `strokes` document, assigned to the configured
  `flat_group_name`.

Both require normalized top-left/right/down axes, complete canvas metadata,
globally unique non-empty stroke IDs, unique positive order numbers within a
group, at least two finite in-canvas points, and explicit `closed` booleans.
Groups retain input order; strokes are executed in numeric `order`. A closed
flag is retained but does not synthesize an extra closing segment.

## Local configuration

Copy [the safe example](../../config/drawing.example.json) to the ignored
`config/drawing.local.json`, then review its local values. The four P1-P4 joint
vectors are transcribed from the delivered `point.json` and remain data, not
Python constants. The delivered five drawing groups use four physical pens:
yellow maps to P1, purple to P2, pink and black both map to P3, and green maps to
P4. Every input group must have an explicit mapping to one of exactly these four
slots before planning succeeds.

The rack configuration also preserves the delivered controller operations:

- normal pickup and between-color return depth: 60 mm;
- final `guiwei` return depth: 30 mm;
- gripper open width: 60 mm;
- gripper closed width: 1 mm.

All four values remain configurable because the original 60/30 difference is
intentional project behavior, not something the PC planner should silently
normalize. P1-P4 were taught with User 0 / Tool 0; physical validity still
requires confirmation before motion.

`production_ready` remains false during offline planning. The separate guarded
Baseline executor requires a separately reviewed true value plus explicit
attended admission; preview never consumes it as motion permission.

The physical conversion is explicit:

```text
User Y relative = u / normalized_width * canvas_width_mm
                  + user_y_offset_mm + json_axis_offset_mm
User Z relative = (1 - v / normalized_height) * canvas_height_mm
                  + user_z_offset_mm
planned User Y absolute = home_pose_user_y_mm + User Y relative
```

This reproduces the source project's configurable relative Y/Z drawing plane
without pretending that the unverified home Cartesian pose is known. The JSON
axis offset is supplied per localization generation; it changes each stroke's
anchor but cancels from within-stroke deltas.

The shared motion profile also follows the delivered controller source. Stroke
segments explicitly carry `speed_pct=12` and `blend_pct=100`. Per the project
owner's clarified defaults, Home, anchor, pen-down/up and rack movements carry
`speed_pct=50`, and every arm motion carries `accel_pct=20`. Baseline,
Localized Baseline and Advanced consume this same plan; only their chassis
relocation strategy differs. The upgraded primitive route carries
`blend_pct=100` through MaixCam
and RPA2 to the controller's `RelMovLUser` `cp` option.

## Preview

```powershell
python app/drawing_task.py dataset/dobot-generation-1.json `
  --config config/drawing.local.json `
  --json-axis-offset-mm 0
```

Add `--show-steps` to print each abstract step or `--output-plan <new-file>` to
write a review artifact. An existing output is never overwritten. The summary
shows both canvas metadata and configured executed size so the archive's
210-versus-150 mm discrepancy remains visible.

The plan contains `pen.select`, `pen.return`, `arm.home`, `arm.relative`, `sleep`,
and `reposition.required` steps. Each pen step now carries the configured rack
joint target, relative Z descent/retract and gripper recipe for a future guarded
executor. A change between different slots returns the current pen at 60 mm and
picks the next at 60 mm; the final return uses 30 mm and ends at the configured
home joints. Adjacent groups mapped to the same slot do not trigger a redundant
return/pick cycle.

## Reachability and checkpoints

Every point endpoint is checked before its motion step is emitted. If the first
point is outside the configured User-Y range, the plan contains only a
reposition barrier. If a later segment would leave the range, the partial plan
first lifts the pen, returns it to the configured rack slot, and finishes at the
configured home pose, then emits:

- the exact group, stroke and next-point checkpoint;
- the endpoint range that must fit after relocation;
- the full feasible JSON-offset delta interval and a midpoint suggestion;
- explicit requirements for pen-up, arm-safe state and a new localization
  generation.

Resume planning starts at the previous point as a pen-down anchor and continues
with the checkpointed segment. Input points are immutable. If one segment is
wider than the configured User-Y workspace, planning rejects it instead of
creating an endless reposition cycle.

Checkpoints do not authorize automatic recovery. The future executor must stop
on `FAULT`, `REJECTED`, `UNKNOWN`, timeout or disconnect, record the checkpoint,
and wait for physical inspection and a new explicit task decision.

## Remaining boundary

`app/baseline_run.py` can execute a complete, arm-only plan after strict status,
configuration, hash, logging and attended-safety gates. It flattens rack recipes
and stops on the first non-`DONE` outcome without retry. It deliberately rejects
plans containing a reposition barrier and never connects to the chassis.

`app/localized_baseline_run.py` now provides the explicit direct-drive plus
AprilTag multi-window path. It returns the pen between windows so checkpoint
planning does not depend on hidden gripper state, requires a fresh localization
generation after every move, and never uses commanded travel as the resumed
offset. Its dry-run is L1 only; real coordinated behavior remains unvalidated
L4. For the supplied job, flattening
adds rack/gripper actions to the 5,220 top-level arm primitives, producing 5,257
actual arm requests and 878 local wait steps. Full-job performance must be
measured rather than hidden by increasing motion speed.
