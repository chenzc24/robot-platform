from __future__ import annotations

import argparse

import uvicorn

from app.main import app


def main() -> None:
    parser = argparse.ArgumentParser(description="Stroke Review local model service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        access_log=False,
        log_level="warning",
        # The companion is a windowed PyInstaller executable. Its stdout and
        # stderr may be None, which breaks Uvicorn's default color formatter.
        # The desktop launcher already redirects process output to desktop.log.
        log_config=None,
    )


if __name__ == "__main__":
    main()
