"""Convert a Dobot project var.py literal to canonical grouped JSON safely."""

import argparse
import ast
import json
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONSOLE_SOURCE = ROOT / "src" / "console"
if str(CONSOLE_SOURCE) not in sys.path:
    sys.path.insert(0, str(CONSOLE_SOURCE))

from drawing.loader import canonical_document, parse_drawing_document
from drawing.models import DrawingError


MAX_VAR_BYTES = 5 * 1024 * 1024


def _read_var_source(source):
    source = Path(source)
    if source.is_dir():
        candidate = source / "var.py"
        if not candidate.is_file():
            raise DrawingError("project directory must contain var.py")
        data = candidate.read_bytes()
        label = str(candidate)
    elif source.is_file() and source.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(source) as archive:
                candidates = [
                    info
                    for info in archive.infolist()
                    if not info.is_dir() and Path(info.filename).name.lower() == "var.py"
                ]
                if len(candidates) != 1:
                    raise DrawingError("ZIP must contain exactly one var.py")
                info = candidates[0]
                if info.file_size > MAX_VAR_BYTES:
                    raise DrawingError("var.py exceeds the import size limit")
                data = archive.read(info)
                label = "%s:%s" % (source, info.filename)
        except (OSError, zipfile.BadZipFile, RuntimeError) as error:
            raise DrawingError("cannot read Dobot ZIP: %s" % type(error).__name__)
    elif source.is_file() and source.name.lower() == "var.py":
        data = source.read_bytes()
        label = str(source)
    else:
        raise DrawingError("source must be a Dobot ZIP, project directory, or var.py")
    if len(data) > MAX_VAR_BYTES:
        raise DrawingError("var.py exceeds the import size limit")
    try:
        return data.decode("utf-8-sig"), label
    except UnicodeError:
        raise DrawingError("var.py must be UTF-8 text")


def parse_var_literal(source_text, label="var.py"):
    """Accept exactly ``data = <literal>``; never compile, import, or execute it."""
    try:
        module = ast.parse(source_text, filename=label, mode="exec")
    except SyntaxError:
        raise DrawingError("var.py is not valid Python syntax")
    if len(module.body) != 1 or not isinstance(module.body[0], ast.Assign):
        raise DrawingError("var.py must contain exactly one data assignment")
    assignment = module.body[0]
    if (
        len(assignment.targets) != 1
        or not isinstance(assignment.targets[0], ast.Name)
        or assignment.targets[0].id != "data"
    ):
        raise DrawingError("var.py must assign exactly the name data")
    try:
        value = ast.literal_eval(assignment.value)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        raise DrawingError("data must contain literals only")
    if not isinstance(value, dict):
        raise DrawingError("data must be an object literal")
    return value


def import_dobot_drawing(source, output, overwrite=False):
    source_text, label = _read_var_source(source)
    document = parse_var_literal(source_text, label)
    job = parse_drawing_document(document)
    canonical = canonical_document(job)
    output = Path(output)
    if output.exists() and not overwrite:
        raise DrawingError("output already exists; use --overwrite explicitly")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(canonical, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "output": str(output.resolve()),
        "source_shape": job.source_shape,
        "groups": len(job.groups),
        "strokes": job.stroke_count,
        "points": job.point_count,
        "canonical_sha256": job.canonical_sha256,
    }


def argument_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv=None):
    try:
        args = argument_parser().parse_args(argv)
        result = import_dobot_drawing(args.source, args.output, args.overwrite)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (DrawingError, OSError) as error:
        print("ERROR: %s" % error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
