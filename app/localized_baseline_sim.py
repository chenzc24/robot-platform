"""Generate a self-contained no-device Localized Baseline rehearsal report."""

import argparse
import json
import sys
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONSOLE_SOURCE = ROOT / "src" / "console"
if str(CONSOLE_SOURCE) not in sys.path:
    sys.path.insert(0, str(CONSOLE_SOURCE))

from drawing import (
    DrawingError,
    load_drawing_site_config,
    load_drawing_job,
    simulate_localized_baseline,
)


def _comma_floats(value):
    try:
        result = tuple(float(item.strip()) for item in value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "expected comma-separated finite numbers"
        ) from error
    if not result:
        raise argparse.ArgumentTypeError("at least one localization error is required")
    return result


def argument_parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "drawing_path",
        nargs="?",
        type=Path,
        default=ROOT / "dataset" / "dobot-generation-1.json",
    )
    result.add_argument(
        "--site-config",
        type=Path,
        default=ROOT / "config" / "drawing.example.json",
    )
    result.add_argument(
        "--output",
        type=Path,
        default=ROOT / "tmp" / "localized-baseline-rehearsal.html",
    )
    result.add_argument("--rail-reference-mm", type=float)
    result.add_argument("--initial-rail-position-mm", type=float)
    result.add_argument("--json-mm-per-rail-mm", type=float)
    result.add_argument("--simulated-reachable-min-mm", type=float)
    result.add_argument("--simulated-reachable-max-mm", type=float)
    result.add_argument("--motion-gain", type=float, default=1.0)
    result.add_argument("--stop-overshoot-mm", type=float, default=0.0)
    result.add_argument(
        "--localization-errors-mm", type=_comma_floats, default=(0.0,)
    )
    result.add_argument("--rail-min-mm", type=float)
    result.add_argument("--rail-max-mm", type=float)
    result.add_argument("--max-windows", type=int, default=100)
    result.add_argument("--open", action="store_true", dest="open_report")
    result.add_argument("--force", action="store_true")
    return result


def build_rehearsal(args):
    site = load_drawing_site_config(args.site_config)
    config = site.drawing
    control_config = site.control
    job = load_drawing_job(
        args.drawing_path, flat_group_name=config.flat_group_name
    )
    return simulate_localized_baseline(
        job,
        config,
        control_config,
        rail_reference_mm=(
            site.rail.json_origin_rail_position_mm
            if args.rail_reference_mm is None else args.rail_reference_mm
        ),
        initial_rail_position_mm=args.initial_rail_position_mm,
        json_mm_per_rail_mm=args.json_mm_per_rail_mm,
        reachable_min_mm=args.simulated_reachable_min_mm,
        reachable_max_mm=args.simulated_reachable_max_mm,
        motion_gain=args.motion_gain,
        stop_overshoot_mm=args.stop_overshoot_mm,
        localization_errors_mm=args.localization_errors_mm,
        rail_min_mm=(
            (site.rail.physical_start_mm
             if site.rail.physical_travel_mm is not None
             else None) if args.rail_min_mm is None
            else args.rail_min_mm
        ),
        rail_max_mm=((
            None if site.rail.physical_travel_mm is None
            else site.rail.physical_start_mm + site.rail.physical_travel_mm
        ) if args.rail_max_mm is None else args.rail_max_mm),
        max_windows=args.max_windows,
    )


def write_report(simulation, output_path, force=False):
    output_path = Path(output_path)
    if output_path.exists() and not force:
        raise DrawingError("output report already exists; use --force to replace it")
    template = (ROOT / "app" / "localized-baseline-simulator.html").read_text(
        encoding="utf-8"
    )
    marker = "__LOCALIZED_BASELINE_SIMULATION_DATA__"
    if template.count(marker) != 1:
        raise DrawingError("simulator template data marker is invalid")
    encoded = json.dumps(
        simulation, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).replace("</", "<\\/")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(template.replace(marker, encoded), encoding="utf-8")
    return output_path.resolve()


def main(argv=None):
    try:
        args = argument_parser().parse_args(argv)
        simulation = build_rehearsal(args)
        output = write_report(simulation, args.output, force=args.force)
        print(
            json.dumps(
                {
                    **simulation["summary"],
                    "mode": "localized_baseline",
                    "simulation_only": True,
                    "source_config_reach_overridden": simulation[
                        "source_config_reach_overridden"
                    ],
                    "report": str(output),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        print("SIMULATION_ONLY no runtime config, device connection, or motion")
        if args.open_report:
            webbrowser.open(output.as_uri())
        return 0
    except (DrawingError, OSError, UnicodeError, ValueError) as error:
        print("ERROR: %s" % error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
