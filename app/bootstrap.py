"""Process-local AMD runtime setup. CPU ASR never imports this module."""
import json
import os
from pathlib import Path
from settings import ROOT, config_path

_dll_handles = []


def setup():
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("HF_HOME", str(ROOT / "cache" / "huggingface"))
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    config = json.loads(config_path().read_text(encoding="utf-8")) if config_path().is_file() else {}
    installation = os.environ.get("RYZEN_AI_INSTALLATION_PATH") or config.get("amd_installation_path")
    environment = config.get("amd_environment") or os.environ.get("CONDA_PREFIX")
    paths = []
    if installation:
        os.environ.setdefault("RYZEN_AI_INSTALLATION_PATH", installation)
        paths.extend([Path(installation) / "onnxruntime/bin", Path(installation) / "onnxruntime_genai"])
    if environment:
        paths.append(Path(environment) / "Library/bin")
    for path in paths:
        if path.is_dir():
            os.environ["PATH"] = str(path) + os.pathsep + os.environ.get("PATH", "")
            if hasattr(os, "add_dll_directory"):
                _dll_handles.append(os.add_dll_directory(str(path)))


setup()
