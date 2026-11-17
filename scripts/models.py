"""Download or verify pinned external models; Python standard library only."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def destination(base, relative):
    parts = PurePosixPath(relative)
    if parts.is_absolute() or not parts.parts or any(p in (".", "..") for p in parts.parts) or "\\" in relative or ":" in relative:
        raise ValueError("Unsafe model path")
    base = Path(base).absolute()
    if base.is_symlink():
        raise ValueError("Model directory must not be a symlink")
    path = base
    for part in parts.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Model path contains a symlink")
    return path


def matches(path, spec):
    if not path.is_file() or path.stat().st_size != spec["size"]:
        return False
    if spec["algorithm"] == "git-sha1":
        digest = hashlib.sha1()
        digest.update(f'blob {spec["size"]}\0'.encode())
    elif spec["algorithm"] == "sha256":
        digest = hashlib.sha256()
    else:
        raise ValueError("Unknown digest algorithm")
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest() == spec["digest"]


def download(path, spec):
    if not spec["url"].startswith("https://"):
        raise ValueError("Model downloads require HTTPS")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".part", dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as output:
            with urllib.request.urlopen(spec["url"], timeout=120) as response:
                size = 0
                while block := response.read(1024 * 1024):
                    size += len(block)
                    if size > spec["size"]:
                        raise ValueError("Downloaded file exceeds expected size")
                    output.write(block)
        if not matches(temporary, spec):
            raise ValueError("Model integrity check failed")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("download", "verify", "list"))
    parser.add_argument("--model", choices=("all", "qwen", "sensevoice", "silero"), default="all")
    parser.add_argument("--accept-model-terms", action="store_true")
    args = parser.parse_args()
    if args.action == "download" and not args.accept_model_terms:
        parser.error("Read docs/MODELS.md and upstream terms first, then pass --accept-model-terms")
    manifest = json.loads((ROOT / "manifests/models.json").read_text())
    failures = 0
    for model in manifest["models"]:
        if args.model not in ("all", model["id"]):
            continue
        print(f'{model["id"]}: {len(model["files"])} files, {sum(f["size"] for f in model["files"]):,} bytes, revision {model["revision"]}')
        if args.action == "list":
            continue
        for spec in model["files"]:
            path = destination(ROOT / "models", spec["path"])
            if matches(path, spec):
                continue
            if args.action == "download":
                print("Downloading " + spec["path"], flush=True)
                download(path, spec)
            else:
                print("Missing or changed: " + spec["path"])
                failures += 1
    if failures:
        raise SystemExit(1)
    print("Done. Verification checks files only; it does not validate NPU execution.")


if __name__ == "__main__":
    main()
