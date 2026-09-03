"""PC-side JSON drawing demo. Preview by default; never retries arm motion.

Run from the repository with Python 3.10+: python app/demo.py --help.
The existing MaixCam endpoint executes one primitive at a time, without cp=100.
"""

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / "protocol", ROOT / "src" / "console"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from maixcam_arm_client import MaixCamArmClient, MaixCamArmClientError, open_connection
from runtime_config import load_runtime_config
from status_mapping import parse_arm_status


class DemoError(ValueError):
    """Invalid drawing data or an execution that must not continue."""


def finite_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DemoError(f"{label} must be a finite number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise DemoError(f"{label} must be a finite number")
    return value


@dataclass(frozen=True)
class DrawingConfig:
    home_joints: tuple = (-120, 0, -90, -90, -30, 90)
    canvas_mm: float = 100.0
    offset_y_mm: float = -30.0
    offset_z_mm: float = -30.0
    pen_travel_mm: float = 20.0
    gripper_mm: int = 1
    user: int = 0
    tool: int = 0
    draw_speed: int = 15
    travel_speed: int = 5
    accel: int = 5

    def __post_init__(self):
        if len(self.home_joints) != 6:
            raise DemoError("home_joints must contain six angles")
        for value in self.home_joints:
            finite_number(value, "home_joints")
        for name in ("canvas_mm", "offset_y_mm", "offset_z_mm", "pen_travel_mm"):
            finite_number(getattr(self, name), name)
        if self.canvas_mm <= 0 or self.pen_travel_mm <= 0:
            raise DemoError("canvas_mm and pen_travel_mm must be positive")
        for name, low, high in (("gripper_mm", 0, 70), ("user", 0, 9),
                                ("tool", 0, 9), ("draw_speed", 1, 100),
                                ("travel_speed", 1, 100), ("accel", 1, 100)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise DemoError(f"{name} must be an integer in {low}..{high}")


@dataclass(frozen=True)
class Stroke:
    order: int
    points: tuple


@dataclass(frozen=True)
class Step:
    name: str
    payload: dict
    label: str


def load_strokes(path):
    """Read the supplied version 1.0 format; reject ambiguous geometry up front."""
    document = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(document, dict) or document.get("version") != "1.0":
        raise DemoError("expected a version 1.0 stroke document")
    if document.get("coordinate_space") != "normalized":
        raise DemoError("coordinate_space must be normalized")
    if document.get("axis") != {"origin": "top-left", "x_positive": "right", "y_positive": "down"}:
        raise DemoError("expected top-left, right/down image axes")
    canvas = document.get("canvas")
    if not isinstance(canvas, dict):
        raise DemoError("canvas must be an object")
    for name in ("width", "height"):
        if finite_number(canvas.get(name), f"canvas.{name}") != 1:
            raise DemoError("normalized canvas width and height must be 1")
    raw_strokes = document.get("strokes")
    if not isinstance(raw_strokes, list):
        raise DemoError("strokes must be an array")
    strokes, orders = [], set()
    for index, raw in enumerate(raw_strokes):
        if not isinstance(raw, dict):
            raise DemoError(f"stroke {index} must be an object")
        order = raw.get("order")
        if type(order) is not int or order <= 0 or order in orders:
            raise DemoError("stroke orders must be unique positive integers")
        orders.add(order)
        if not isinstance(raw.get("points"), list):
            raise DemoError(f"stroke {order}: points must be an array")
        points = []
        for point_index, point in enumerate(raw["points"]):
            label = f"stroke {order}, point {point_index}"
            if not isinstance(point, list) or len(point) != 2:
                raise DemoError(f"{label}: expected [u, v]")
            for value in point:
                if not 0 <= finite_number(value, label) <= 1:
                    raise DemoError(f"{label}: coordinates must be in 0..1")
            points.append(tuple(point))
        strokes.append(Stroke(order, tuple(points)))
    return tuple(sorted(strokes, key=lambda stroke: stroke.order))


def line_draw(stroke, config):
    """Translate the original line_draw into ordered, unsent PC commands."""
    points = stroke.points
    if len(points) < 2:
        return []
    prefix = f"stroke {stroke.order}"
    travel = {"accel_pct": config.accel, "speed_pct": config.travel_speed}
    steps = [Step("arm.move_joint", {"joint_deg": list(config.home_joints), **travel}, f"{prefix}: home"),
             Step("sleep", {"seconds": 0.2}, f"{prefix}: home pause")]

    def relative(translation, label, speed):
        for value in translation:
            finite_number(value, f"{prefix}: {label}")
        steps.append(Step("arm.jog_xyz", {
            "translation_mm": list(translation), "user": config.user,
            "tool": config.tool, "accel_pct": config.accel, "speed_pct": speed,
        }, f"{prefix}: {label}"))

    u, v = points[0]
    relative((0, u * config.canvas_mm + config.offset_y_mm,
              (1 - v) * config.canvas_mm + config.offset_z_mm),
             "first point", config.travel_speed)
    relative((-config.pen_travel_mm, 0, 0), "pen down", config.travel_speed)
    for index in range(1, len(points)):
        previous, current = points[index - 1], points[index]
        relative((0, (current[0] - previous[0]) * config.canvas_mm,
                  (previous[1] - current[1]) * config.canvas_mm),
                 f"point {index}", config.draw_speed)
    relative((config.pen_travel_mm, 0, 0), "pen up", config.travel_speed)
    steps.append(Step("sleep", {"seconds": 0.3}, f"{prefix}: end pause"))
    return steps


def build_plan(strokes, config):
    drawable = [stroke for stroke in strokes if len(stroke.points) >= 2]
    if not drawable:
        raise DemoError("no strokes with at least two points; nothing will be sent")
    steps = [Step("arm.gripper", {"width_mm": config.gripper_mm}, "set gripper")]
    for stroke in drawable:
        steps.extend(line_draw(stroke, config))
    return steps


def require_done(responses, label):
    if not isinstance(responses, (list, tuple)) or not responses:
        raise DemoError(f"{label}: missing terminal response; outcome unknown")
    terminal = responses[-1]
    if not isinstance(terminal, dict) or not isinstance(terminal.get("payload"), dict):
        raise DemoError(f"{label}: malformed terminal response; outcome unknown")
    state = terminal.get("lifecycle")
    if state != "DONE":
        code = terminal["payload"].get("error_code", "not_completed")
        raise DemoError(f"{label}: {state} ({code}); aborting without retry")


def run_plan(client, steps, sleep=time.sleep, report=print):
    """A DONE advances the sequence; any exception aborts, without cleanup moves."""
    require_done(client.ping(), "ping")
    responses = client.status()
    require_done(responses, "status")
    status = parse_arm_status(responses)
    if (status.control_mode != "yolo" or not status.motion_permitted
            or status.service_state != "ready" or status.active_sequence != 0
            or status.last_error != "none" or not status.feedback_valid):
        raise DemoError("arm must report ready, idle YOLO motion with valid feedback and no error")
    for index, step in enumerate(steps, 1):
        report(f"[{index}/{len(steps)}] {step.label}")
        if step.name == "sleep":
            sleep(step.payload["seconds"])
            continue
        responses = client.command(step.name, step.payload, ttl_ms=60000)
        require_done(responses, step.label)


def argument_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path", nargs="?", type=Path,
                        default=ROOT / "dataset" / "strokes_railway_new.json")
    parser.add_argument("--execute", action="store_true", help="send commands after an attended safety prompt")
    parser.add_argument("--show-commands", action="store_true", help="print every planned command")
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "console.local.json")
    parser.add_argument("--host", help="MaixCam arm endpoint; requires --port")
    parser.add_argument("--port", type=int, help="MaixCam port; requires --host")
    defaults = DrawingConfig()
    parser.add_argument("--home-joints", type=float, nargs=6, default=defaults.home_joints)
    for name in ("canvas_mm", "offset_y_mm", "offset_z_mm", "pen_travel_mm"):
        parser.add_argument("--" + name.replace("_", "-"), type=float, default=getattr(defaults, name))
    for name in ("gripper_mm", "user", "tool", "draw_speed", "travel_speed", "accel"):
        parser.add_argument("--" + name.replace("_", "-"), type=int, default=getattr(defaults, name))
    return parser


def main(argv=None):
    args = argument_parser().parse_args(argv)
    try:
        config = DrawingConfig(**{name: getattr(args, name) for name in DrawingConfig.__dataclass_fields__})
        strokes = load_strokes(args.json_path)
        steps = build_plan(strokes, config)
        count = sum(step.name != "sleep" for step in steps)
        drawable = sum(len(stroke.points) >= 2 for stroke in strokes)
        print(f"{len(strokes)} strokes, {sum(len(s.points) for s in strokes)} points; "
              f"{drawable} drawable strokes, {count} arm commands.")
        print(f"Canvas: {config.canvas_mm:g} x {config.canvas_mm:g} mm "
              "(JSON target_width_mm/target_height_mm metadata is not used).")
        print(f"User {config.user}, Tool {config.tool}; "
              f"Y={config.canvas_mm:g}*u{config.offset_y_mm:+g}, "
              f"Z={config.canvas_mm:g}*(1-v){config.offset_z_mm:+g}; "
              f"pen down/up: User X -/+{config.pen_travel_mm:g} mm.")
        print(f"Home joints: {list(config.home_joints)}; gripper: {config.gripper_mm} mm; "
              f"draw/travel/accel: {config.draw_speed}/{config.travel_speed}/{config.accel}%.")
        print("Blending is disabled by the existing endpoint: not the original cp=100.")
        if args.show_commands:
            for step in steps:
                print(json.dumps({"label": step.label, "command": step.name, "payload": step.payload}))
        if not args.execute:
            print("PREVIEW ONLY: no connections or commands sent. Add --execute for attended operation.")
            return 0
        if (args.host is None) != (args.port is None):
            raise DemoError("supply both --host and --port, or use --config")
        if args.host is None:
            endpoint = load_runtime_config(args.config).arm
            host, port, timeout = endpoint.host, endpoint.port, endpoint.connect_timeout_seconds
        else:
            host, port, timeout = args.host, args.port, 3.0
        if not host.strip() or not 1024 <= port <= 65535 or not math.isfinite(timeout) or timeout <= 0:
            raise DemoError("configure a valid MaixCam arm endpoint")
        print("Confirm: operator present at physical e-stop; area clear; chassis stopped and "
              "restrained/in the safe area; safe home/path, pen, load, User/Tool and low speeds verified. "
              "Close other arm command sessions first. This includes a gripper move and repeated joint homing. "
              "On error/timeout/Ctrl+C, no more commands or automatic pen lift are sent. "
              "The current primitive may continue: use the physical e-stop if needed.")
        if input("Type DRAW to confirm this attended test, or Enter to cancel: ").strip() != "DRAW":
            print("Cancelled; no connection opened.")
            return 2
        connection = open_connection(host, port, timeout)
        try:
            client = MaixCamArmClient(connection, "drawing-demo")
            run_plan(client, steps)
        finally:
            connection.close()
        print("All commands reported DONE; physical terminal position/drawing accuracy is not verified.")
        return 0
    except (OSError, ValueError, MaixCamArmClientError, EOFError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        print("Aborted; no retries or cleanup motion. If execution began, inspect the arm before restarting.", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted: no further commands; this is NOT a physical emergency stop.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
