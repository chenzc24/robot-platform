"""Compile Python source text without creating bytecode cache files."""

import argparse
import json
import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[2]
LOCAL_SOURCE_EXCLUSIONS = {
    ROOT / "src" / "esp32" / "app" / "secrets.py",
    ROOT / "src" / "esp32" / "app" / "device_config.py",
}


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Files or directories relative to the workspace")
    return parser


def iter_sources(paths):
    for raw_path in paths:
        path = (ROOT / raw_path).resolve()
        if path.is_file() and path.suffix == ".py":
            if path not in LOCAL_SOURCE_EXCLUSIONS:
                yield path
        elif path.is_dir():
            for candidate in sorted(path.rglob("*.py")):
                if (
                    "__pycache__" not in candidate.parts
                    and candidate not in LOCAL_SOURCE_EXCLUSIONS
                ):
                    yield candidate
        else:
            raise FileNotFoundError("Python source path not found: %s" % raw_path)


def check(paths):
    checked = []
    for path in iter_sources(paths):
        source = path.read_text(encoding="utf-8")
        compile(source, str(path), "exec")
        checked.append(path.relative_to(ROOT).as_posix())
    if not checked:
        raise RuntimeError("no Python source files found")
    print(json.dumps({"ok": True, "checked": len(checked)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(check(build_parser().parse_args().paths))
