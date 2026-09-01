"""Command-line entry point for the local simulator console."""

import argparse
import sys

from PySide6.QtWidgets import QApplication

from .views import MainWindow


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Unified robot control console")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Construct the window, verify its safe defaults, and exit.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    application = QApplication.instance() or QApplication(["robot-console"])
    window = MainWindow()
    if args.smoke_test:
        window.run_smoke_assertions()
        window.close()
        return 0
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
