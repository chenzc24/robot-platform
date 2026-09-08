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
`config/drawing.local.json`, then replace every placeholder with reviewed local
values. In particular, the delivered project has five colors but only four
taught rack points and no black-handling branch. Every input group must have an
explicit logical pen-slot mapping before planning succeeds.

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

The plan contains abstract `pen.select`, `pen.return`, `arm.home`, `arm.relative`,
`sleep`, and `reposition.required` steps. Pen actions are not expanded to rack
motions in this stage.

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

This stage does not implement rack poses, gripper actions, arm status gates,
network execution, chassis commands, AprilTag collection, buffered strokes or
the coordinated L4 state machine. Those remain separately reviewed goals. The
current primitive route would require at least 5,220 sequential arm commands
for the supplied drawing before pen and chassis actions, so full-job performance
must be measured rather than hidden by increasing motion speed.
