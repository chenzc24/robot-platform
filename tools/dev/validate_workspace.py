"""Validate local runtime contracts and development entry points."""

import json
import pathlib
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[2]
TASKS_PATH = ROOT / ".vscode" / "tasks.json"
SCHEMA_PATH = ROOT / "protocol" / "runtime-status.schema.json"
SOURCE_ROOTS = (
    ROOT / "src" / "esp32" / "app",
    ROOT / "src" / "maixcam",
    ROOT / "tools",
)
SOURCE_SUFFIXES = {".py", ".ps1", ".sh"}
LOCAL_SOURCE_EXCLUSIONS = {
    ROOT / "src" / "esp32" / "app" / "secrets.py",
    ROOT / "src" / "esp32" / "app" / "device_config.py",
}


def _tracked_files():
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return {item for item in result.stdout.decode("utf-8").split("\0") if item}


def _source_language_violations():
    violations = []
    for source_root in SOURCE_ROOTS:
        for path in source_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
                continue
            if path in LOCAL_SOURCE_EXCLUSIONS or "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for line_number, line in enumerate(text.splitlines(), start=1):
                if any(ord(character) > 127 for character in line):
                    violations.append(
                        "%s:%d" % (path.relative_to(ROOT).as_posix(), line_number)
                    )
    return violations


def validate():
    errors = []
    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    labels = [task["label"] for task in tasks.get("tasks", [])]
    duplicate_labels = sorted({label for label in labels if labels.count(label) > 1})
    if duplicate_labels:
        errors.append("duplicate task labels: %s" % ", ".join(duplicate_labels))

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    required_fields = set(schema.get("required", []))
    if required_fields != set(schema.get("properties", {})):
        errors.append("runtime status required fields and properties differ")

    tracked = _tracked_files()
    forbidden_tracked = sorted(
        path
        for path in tracked
        if path.endswith("secrets.py")
        or path.endswith("device_config.py")
        or "__pycache__" in pathlib.PurePosixPath(path).parts
        or path.endswith(".pyc")
    )
    if forbidden_tracked:
        errors.append("forbidden tracked files: %s" % ", ".join(forbidden_tracked))

    language_violations = _source_language_violations()
    if language_violations:
        errors.append(
            "non-ASCII formal source lines: %s" % ", ".join(language_violations)
        )

    cache_directories = sorted(
        path.relative_to(ROOT).as_posix()
        for source_root in SOURCE_ROOTS
        for path in source_root.rglob("__pycache__")
        if path.is_dir()
    )
    result = {
        "ok": not errors,
        "task_count": len(labels),
        "runtime_status_fields": sorted(required_fields),
        "source_language": "ascii",
        "cache_directories": cache_directories,
        "errors": errors,
    }
    print(json.dumps(result, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(validate())
