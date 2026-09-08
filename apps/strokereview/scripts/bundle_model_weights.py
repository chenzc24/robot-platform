"""Prepare the local line-art weights shipped with the Windows desktop build."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from huggingface_hub import hf_hub_download


REQUIRED_FILES = (
    "ControlNetHED.pth",
    "table5_pidinet.pth",
    "sk_model.pth",
    "sk_model2.pth",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_path(repository: str, filename: str) -> Path:
    local_repository = Path(repository)
    if local_repository.is_dir():
        source = local_repository / filename
        if not source.is_file():
            raise FileNotFoundError(f"Missing model weight: {source}")
        return source
    return Path(hf_hub_download(repo_id=repository, filename=filename))


def bundle_weights(repository: str, output: Path) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, object]] = []
    for filename in REQUIRED_FILES:
        source = _source_path(repository, filename)
        destination = output / filename
        shutil.copy2(source, destination)
        files.append({
            "name": filename,
            "size": destination.stat().st_size,
            "sha256": _sha256(destination),
        })
    manifest: dict[str, object] = {
        "repository": repository,
        "purpose": "Offline Lineart, PiDiNet and HED inference",
        "files": files,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default="lllyasviel/Annotators")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = bundle_weights(args.repository, args.output.resolve())
    total = sum(int(item["size"]) for item in manifest["files"])
    print(f"Bundled {len(REQUIRED_FILES)} model weights ({total / 1024 / 1024:.1f} MiB).")


if __name__ == "__main__":
    main()
