# Expand the drawing canvas to 700 x 200 mm

- Status: complete
- Responsible: joint
- Highest validation level: L1

## Objective

Change the physical drawing canvas from 150 x 150 mm to 700 x 200 mm while
preserving the first-generation arm program's parameterized mapping:

```text
User-Y = 700u - 350 + json_axis_offset_mm
User-Z = 200(1-v) - 133.333333333
```

Keep the colleague-tested User-Y drawing window `[-200,180]` unchanged. The
700 mm width therefore requires checkpointed chassis relocation in normal
Localized Baseline execution.

## Initial audit

- `main` is clean and synchronized with `origin/main` at `b137a0c`.
- The tracked drawing example is 150 x 150 mm with offsets -75 / -100 mm.
- Both ignored local real-sample JSON files declare 210 x 210 mm metadata. The
  unified runner rejects non-uniform mismatch, so their physical target metadata
  will be updated locally for rehearsal but will not enter Git.
- The AprilTag board layout is a separate, ignored, unmeasured 300 x 200 mm
  localization configuration. It remains unchanged in this goal.

## Editable scope

- `config/drawing.example.json`
- ignored local rehearsal inputs `dataset/dobot-generation-1.json` and
  `dataset/strokes_railway_new.json` (metadata only; never staged)
- `app/README.md`
- `docs/console/localized-baseline-simulator.md`
- `docs/console/drawing-control-modes.md`
- `docs/robot-arm/pc-drawing-task.md`
- `src/console/drawing/control_modes.py`
- focused coordinator/control-mode tests required for bounded relocation hops
- this plan and append-only `plan/log.md`

## Read-only scope and dependencies

- Production planner, coordinator and device source remain read-only. The
  relocation adapter may bound a planner-centering suggestion to the configured
  per-hop distance; its direct distance guard remains unchanged.
- AprilTag board/camera calibration and all `*.local.*` files remain read-only.
- Device filesystems and protected raw archives remain untouched.

## Validation

- Parse drawing and control configuration.
- Exact JSON-to-board size validation for both tracked real samples.
- Run the production-path Localized Baseline rehearsal on the 700 x 200 mm
  sample without overriding the `[-200,180]` window.
- Focused drawing/planner/simulator/runner tests, Python/JSON checks, full L1
  repository test discovery, `git diff --check`, scoped diff and status audit.

## Safety

- L1 only. No hardware discovery, connection, command, configuration write,
  deployment, service action or motion.
- X/Z safety limits, joint paths, collision analysis and moving-arm envelope are
  outside this goal at the user's direction.

## Commit intent

Commit and push the bounded canvas update directly to the sole `main` branch.

## Actual results

- Drawing geometry is 700 x 200 mm with offsets -350 mm and
  -133.333333333 mm. The resulting mapping is `Y=700u-350+offset` and
  `Z=200(1-v)-133.333333333`; the colleague-tested User-Y window remains
  `[-200,180]`.
- The production relocation adapter now bounds planner-centering suggestions to
  the configured 300 mm per-hop limit. It still stops and uses the measured
  localization result before replanning; direct relocator calls beyond the
  limit remain rejected.
- Both ignored local samples parse as 700 x 200 mm. The grouped 439-stroke,
  3,903-point sample passed unified dry-run size validation. The flat sample
  reached its pre-existing missing `default` pen-slot mapping after size
  validation; no pen choice was inferred in this goal.
- The ideal production-path Localized Baseline rehearsal completed in six
  drawing windows with five relocations, three direction changes and
  1,215.8966 mm total absolute rail travel. It used the source reach with no
  override. The declared-error scenario also completed in six windows with
  five relocations.
- L1 passed JSON parsing, Python compilation, 13 focused control-mode tests,
  the full 386-test repository suite, `git diff --check`, diff and status audit.
- No hardware discovery, connection, command, configuration write, deployment,
  service action or motion occurred. The ignored local AprilTag board layout
  remains unchanged.
