"""Launch the local web console."""

import argparse
import sys
import webbrowser

from runtime_config import RuntimeConfigError, load_runtime_config

from .runtime import WebConsoleRuntime
from .server import create_server


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Localhost robot control console")
    parser.add_argument("--config", default="config/console.local.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8080, type=int)
    parser.add_argument("--event-log", default="logs/console/web-events.log")
    parser.add_argument("--open", action="store_true", help="Open the console in the default browser")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        config = load_runtime_config(args.config)
        runtime = WebConsoleRuntime(config, event_log_path=args.event_log or None)
        server = create_server(runtime, args.host, args.port)
    except (RuntimeConfigError, OSError, ValueError) as error:
        print("Cannot start web console: %s" % error, file=sys.stderr)
        return 2
    url = "http://%s:%d/" % server.server_address
    print("Robot Console: %s" % url, flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        runtime.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
