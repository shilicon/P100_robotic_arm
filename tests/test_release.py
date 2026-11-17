import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

from support import ROOT, configuration
from export_public import collect, audit, export
from models import destination, matches


class ReleaseTests(unittest.TestCase):
    def test_private_runtime_files_excluded_and_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in (".private/vendor.cc", "models/weight.bin", "logs/chat.txt", "app/server.py"):
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("test")
            self.assertEqual([p.relative_to(root).as_posix() for p in collect(root)], ["app/server.py"])
            (root / "app/leak.py").symlink_to(root / ".private/vendor.cc")
            with self.assertRaises(ValueError): collect(root)

    def test_configuration_secret_in_allowed_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); config = configuration()
            (root / "config.json").write_text(json.dumps(config))
            (root / "README.md").write_text(config["api_key"])
            with self.assertRaises(ValueError): audit(root, collect(root))

    def test_real_public_package_and_hash_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "public.zip"
            count = export(ROOT, archive)
            self.assertGreater(count, 30)
            with zipfile.ZipFile(archive) as source:
                hashes = json.loads(source.read("SOURCE_SHA256.json"))
                self.assertEqual(set(source.namelist()), set(hashes) | {"SOURCE_SHA256.json"})
                for name, digest in hashes.items():
                    self.assertEqual(hashlib.sha256(source.read(name)).hexdigest(), digest)
                    self.assertNotIn(".private", name)
                    self.assertNotEqual(name, "config.json")

    def test_model_paths_and_integrity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for path in ("../secret", "/absolute", "a/../../secret", "a\\secret", "C:/secret"):
                with self.assertRaises(ValueError): destination(root, path)
            file = destination(root, "model"); file.write_bytes(b"test")
            for algorithm, digest in (("sha256", hashlib.sha256(b"test").hexdigest()),
                                       ("git-sha1", hashlib.sha1(b"blob 4\0test").hexdigest())):
                spec = {"size": 4, "algorithm": algorithm, "digest": digest}
                self.assertTrue(matches(file, spec))
                file.write_bytes(b"fail"); self.assertFalse(matches(file, spec)); file.write_bytes(b"test")
            (root / "link").symlink_to(root, target_is_directory=True)
            with self.assertRaises(ValueError): destination(root, "link/model")

    def test_cpp_firmware_token_gate(self):
        compiler = shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
        if not compiler:
            self.skipTest("C++ compiler required for portable firmware authentication test")
        with tempfile.TemporaryDirectory() as folder:
            executable = Path(folder) / "bearer-test"
            subprocess.run([compiler, "-std=c++11", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "firmware-integration"),
                            str(ROOT / "tests/bearer_auth.cc"), "-o", str(executable)], check=True, timeout=30)
            subprocess.run([str(executable)], check=True, timeout=10)
