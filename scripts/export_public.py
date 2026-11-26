"""Build a source-only public ZIP from an explicit allowlist."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = {"README.md", "README.en.md", "LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", "SECURITY.md", "CONTRIBUTING.md",
         ".gitignore", "config.example.json", "requirements.txt", "requirements-asr.txt", "requirements-test.txt"}
DIRECTORIES = {"app": {".py"}, "scripts": {".py", ".ps1"}, "tests": {".py", ".json", ".cc"},
               "prompts": {".txt"}, "docs": {".md"}, "firmware-integration": {".h", ".md"},
               "manifests": {".json"}, ".github": {".yml", ".yaml"}, "website": {".html"}}
SENSITIVE = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{30,}|\bAKIA[A-Z0-9]{16}\b")


def collect(root):
    root = Path(root)
    result = []
    for name in sorted(FILES):
        file = root / name
        if file.is_symlink():
            raise ValueError("Symlink in public files: " + name)
        if file.is_file():
            result.append(file)
    for name, extensions in DIRECTORIES.items():
        folder = root / name
        if folder.is_symlink():
            raise ValueError("Symlink in public directories: " + name)
        if not folder.exists():
            continue
        for path in sorted(folder.rglob("*")):
            if path.is_symlink():
                raise ValueError("Symlink in public tree: " + str(path.relative_to(root)))
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            if path.is_file():
                relative = path.relative_to(root)
                if any(p.startswith(".") for p in relative.parts[1:]) or path.suffix not in extensions:
                    raise ValueError("Unexpected public file: " + str(relative))
                if path.name in ("config.json", "local_service_config.h"):
                    raise ValueError("Private configuration in public tree")
                result.append(path)
    return sorted(result)


def audit(root, files):
    root = Path(root)
    secrets = []
    private = root / "config.json"
    if private.is_file():
        data = json.loads(private.read_text(encoding="utf-8"))
        secrets = [data.get(k, "") for k in ("api_key", "robot_api_key")]
    for path in files:
        relative = str(path.relative_to(root))
        if path.stat().st_size > 1024 * 1024:
            raise ValueError("File too large for public source: " + relative)
        content = path.read_text(encoding="utf-8")
        if "\x00" in content or SENSITIVE.search(content) or any(s and s in content for s in secrets):
            raise ValueError("Possible secret or binary content: " + relative)


def export(root, output):
    root, output = Path(root), Path(output)
    files = collect(root)
    required = FILES | {"app/server.py", "scripts/configure.py", "manifests/models.json", "prompts/robot.txt"}
    missing = required - {p.relative_to(root).as_posix() for p in files}
    if missing:
        raise ValueError("Missing release files: " + ", ".join(sorted(missing)))
    audit(root, files)
    output.parent.mkdir(parents=True, exist_ok=True)
    hashes = {}
    # Exclusive creation avoids silently replacing an earlier reviewed archive.
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            data = path.read_bytes()
            name = path.relative_to(root).as_posix()
            archive.writestr(name, data)
            hashes[name] = hashlib.sha256(data).hexdigest()
        archive.writestr("SOURCE_SHA256.json", json.dumps(hashes, indent=2) + "\n")
    return len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/public-source.zip")
    parser.add_argument("--check", action="store_true", help="Audit without writing a ZIP")
    args = parser.parse_args()
    if args.check:
        files = collect(ROOT)
        audit(ROOT, files)
        print(f"Audited {len(files)} public source files. This is not a complete secret or license audit.")
    else:
        count = export(ROOT, args.output)
        print(f"Exported {count} source files to {args.output}")


if __name__ == "__main__":
    main()
