"""Temporary test credentials never use the developer's private configuration."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "scripts"))


def configuration():
    data = json.loads((ROOT / "config.example.json").read_text())
    data.update(api_key=secrets.token_urlsafe(32), robot_api_key=secrets.token_urlsafe(32))
    return data


@contextmanager
def configured_server():
    data = configuration()
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "config.json"
        path.write_text(json.dumps(data))
        with patch.dict(os.environ, {"RIG_CONFIG": str(path)}):
            import server
            with patch.object(server, "CONFIG", data):
                yield server
