# PC drawing demo

`demo.py` reads `dataset/strokes_railway_new.json` and sends existing
`MaixCamArmClient` commands through PC -> MaixCam -> TCP232 -> Dobot LAN1.
It does not deploy a new controller project or use LAN2 as a runtime route.
Python 3.10+ and the repository sources are sufficient; no new packages.

## Preview (no hardware)

From the repository root:

```powershell
python app/demo.py
python app/demo.py dataset/strokes_railway_new.json --show-commands
```

The default dataset path is resolved relative to this repository even when
launched from another working directory. Explicit relative paths use the
current working directory. `dataset/` is ignored; obtain the point file locally
after cloning. Tests use synthetic points, not a committed copy of the dataset.

## Mapping retained from the supplied demo

The JSON uses version `1.0`, `coordinate_space: normalized`, a unit canvas,
top-left origin, X right, Y down, and `strokes` containing `order` and `points`.
Orders must be unique positive integers and are executed in numeric order.
Every point must be a finite `[u, v]` pair in `[0, 1]`. The entire input is
validated before connecting. Strokes with fewer than two points are skipped;
all-empty data sends nothing. No filtering is enabled (the supplied demo did
not call its filter function). Point order, duplicates and endpoints are kept.

The default sequence is:

1. `arm.gripper(width_mm=1)` once.
2. For each drawable stroke, `arm.move_joint([-120, 0, -90, -90, -30, 90])`;
   wait for DONE, then pause 0.2 seconds.
3. `arm.jog_xyz([0, 100*u0-30, 100*(1-v0)-30])` to the first point.
4. `arm.jog_xyz([-20, 0, 0])` to lower the pen along User -X.
5. For each subsequent point: `[0, 100*(u-u_prev), 100*(v_prev-v)]`.
6. `arm.jog_xyz([20, 0, 0])` to lift; pause 0.3 seconds after DONE.

All translations use the same explicit User/Tool IDs (defaults 0/0). This is
a relative YZ drawing plane, **not** camera calibration or an absolute paper
coordinate system. The home-joint pose defines the reference for each stroke.
Confirm pen clearance during repeated joint homing and the sign of the pen axis.

The supplied JSON says 210 x 210 mm, but the original code scales by 100.
Execution deliberately keeps **100 x 100 mm** and ignores target-size metadata;
it does not automatically enlarge the physical workspace. Use `--canvas-mm`
only after separately checking reachability, pen alignment and workspace safety.
`--offset-y-mm`, `--offset-z-mm`, `--pen-travel-mm`, `--home-joints`, `--user`,
`--tool` and `--gripper-mm` are explicit local geometry/tool overrides, not
controller calibration writes.

## Known differences and limits

- The existing route disables blending, so the original `cp=100` is **not**
  reproduced. Every primitive waits for its own DONE; small segments may pause
  and network/controller latency may dominate drawing time. No queued smooth
  trajectory is claimed. That feature requires a separate cross-device change.
- Drawing speed is 15%; travel speed and acceleration explicitly default to 5%
  because the original unspecified device defaults are unknown. Options are
  `--draw-speed`, `--travel-speed`, `--accel` (integer percentages 1..100).
- Each command has a 60-second completion budget. DONE means the controller
  API returned, **not** verified physical terminal position. Offline tests do
  not prove accuracy, pen pressure, safe reachability or absence of singularity.

## Attended execution (not tested on hardware in this goal)

Use the already deployed YOLO arm runtime described in
`docs/robot-arm/yolo-manual-control.md`. Do not run alongside an active console
arm session or another script. The demo does not take over a session, auto-enable
the controller, clear an alarm, change safety settings, or touch the chassis.
It requires a ready/idle motion-enabled YOLO status, valid feedback and no error.

After verifying the physical setup and the preview, run:

```powershell
python app/demo.py --execute --user 0 --tool 0
```

This reads the ignored `config/console.local.json` arm endpoint. Alternatively,
pass both `--host <maixcam-host>` and `--port <arm-service-port>`. No credentials
or endpoint addresses are embedded in the demo or point file.

The `DRAW` prompt confirms the **current test**: an operator can reach the
physical emergency stop, the area is clear, chassis stop is confirmed and the
chassis is restrained/in the safe area, and home/path/pen/load/frames/speeds are
safe. This software prompt does not replace controller safeguards or the e-stop.

On FAULT, REJECTED, UNKNOWN, timeout or Ctrl+C, stop sending immediately; never
retry a segment or automatically lift/home in cleanup. Closing the socket or
pressing Ctrl+C does **not** cancel an in-flight physical move. Use the physical
e-stop if necessary and inspect the pose/pen before any restart. Restarting runs
the full drawing again; there is no automatic resume.

## Local validation

```powershell
python -m unittest discover -s tests/app -p test_demo.py -v
```
