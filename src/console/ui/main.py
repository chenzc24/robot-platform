"""Command-line entry point for the local simulator console."""

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .controller import ConsoleController
from .runtime import RuntimeCoordinator
from runtime_config import RuntimeConfigError, load_runtime_config
from .views import MainWindow


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Unified robot control console")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Construct the window, verify its safe defaults, and exit.",
    )
    parser.add_argument(
        "--config",
        default="config/console.local.json",
        help="Optional ignored local runtime configuration JSON.",
    )
    parser.add_argument(
        "--event-log",
        default="logs/console/latest-events.log",
        help="Ignored local text log path; set an empty value to disable it.",
    )
    return parser.parse_args(argv)


def _load_optional_runtime(path):
    config_path = Path(path)
    if not config_path.is_file():
        return None
    return RuntimeCoordinator(load_runtime_config(config_path))


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    application = QApplication.instance() or QApplication(["robot-console"])
    try:
        runtime = _load_optional_runtime(args.config)
    except RuntimeConfigError as error:
        print("Local console configuration is invalid: %s" % error, file=sys.stderr)
        return 2
    event_log_path = None if args.smoke_test or not args.event_log else args.event_log
    window = MainWindow(ConsoleController(runtime=runtime, event_log_path=event_log_path))
    if args.smoke_test:
        window.run_smoke_assertions()
        window.close()
        return 0
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
