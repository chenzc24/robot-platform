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

`production_ready` remains false during offline planning. A future executor must
require a separately reviewed true value; this stage never consumes it as
motion permission.

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
first lifts the pen and returns to the configured home pose, then emits:

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

This stage records rack poses and gripper recipes but does not execute them. Arm
status gates, network execution, chassis commands, AprilTag collection, buffered
strokes and the coordinated L4 state machine remain separately reviewed goals.
The current drawing route requires 5,220 sequential drawing-arm primitives for
the supplied job, in addition to pen and chassis actions, so full-job performance
must be measured rather than hidden by increasing motion speed.
