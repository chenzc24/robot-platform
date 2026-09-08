# Apply coworker default motion percentages

- Status: `completed`
- Responsible: `agent`
- Highest validation level: `L1`

## Objective

Apply the project owner's clarified defaults to the single drawing motion
profile shared by Baseline and Advanced: source-explicit stroke speed 12%,
source-explicit stroke blend 100%, otherwise speed 50%, and acceleration 20%
for every arm motion.

## Initial state and ownership

- Clean deployment worktree on `target/coworker-default-motion-options`, based
  on synchronized `origin/main` at `f3d7df1`.
- The primary worktree remains dirty and read-only.
- The previous profile represented unspecified options as `null`; the user has
  now supplied the intended numeric values 50 and 20.

## Modifiable scope

- `config/drawing.example.json`
- ignored `config/drawing.local.json`
- grouped drawing documentation and related planner/config tests
- this plan and append-only `plan/log.md`

## Read-only scope

- planner implementation, relocation strategies, device protocols/runtimes,
  generated artifacts, devices, local credentials and raw-resource archives

## Expected result

- Every planned arm motion carries `accel_pct=20`.
- Stroke segments carry `speed_pct=12, blend_pct=100`.
- Home, anchor, pen, and rack motion carry `speed_pct=50` and no invented
  non-stroke blend value.
- Baseline and Advanced continue to share this exact profile.

## Validation and safety

- L1 configuration/planner/app regressions, real-data preview assertions,
  source/JSON/diff/staged-scope checks.
- No connection, deployment, service action, controller import or motion.
- The existing gateway still blocks nonzero blend; `cp=100` requires a later
  reviewed runtime change before exact hardware execution.

## Actual results

- Set shared drawing configuration to travel/default speed 50% and acceleration
  20%, retaining stroke speed 12% and stroke blend 100%.
- Restored strict integer validation for both clarified defaults; `null` is no
  longer accepted.
- Real-data planning verified all 3,464 stroke segments at speed/blend/accel
  12/100/20 and all 1,342 other arm motions at speed/accel 50/20 with no
  non-stroke blend field.
- L1 passed 23 focused tests and all 114 applicable app/console regressions.
  The 4-file source check, example/local JSON parsing and `git diff --check`
  passed.
- Updated the ignored deployment-worktree `config/drawing.local.json` to the
  same values with its production gate still false.
- No device connection, deployment, service action, controller import,
  configuration write to hardware or motion occurred. `cp=100` remains blocked
  by the current primitive gateway until the separately reviewed runtime change.

## Intent to submit

```text
fix(drawing): apply coworker default motion percentages
```
