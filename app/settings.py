"""Shared configuration; errors never include credential values."""
import json
import ipaddress
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN = re.compile(r"[A-Za-z0-9_-]{32,128}\Z")


def config_path():
    return Path(os.environ.get("RIG_CONFIG", str(ROOT / "config.json"))).resolve()


def load_config():
    path = config_path()
    if not path.is_file():
        raise ValueError("Missing config.json. Run: python scripts/configure.py --lan-host YOUR_PC_IP")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Configuration must be a JSON object")
    try:
        ipaddress.IPv4Address(data.get("lan_host", ""))
    except (ValueError, TypeError):
        raise ValueError("lan_host must be the PC IPv4 address") from None
    for name in ("api_key", "robot_api_key"):
        token = data.get(name, "")
        if not isinstance(token, str) or not TOKEN.fullmatch(token) or token.startswith("GENERATE_"):
            raise ValueError(f"{name} must be a generated 32–128 character URL-safe token")
    if data["api_key"] == data["robot_api_key"]:
        raise ValueError("Service and device tokens must be different")
    if data.get("host") not in ("127.0.0.1", "0.0.0.0", "::1"):
        raise ValueError("host must be 127.0.0.1, ::1 or 0.0.0.0")
    for name, low, high in (("port", 1, 65535), ("llm_max_context", 512, 4096),
                            ("llm_output_tokens", 1, 512), ("llm_chat_input_tokens", 128, 4096),
                            ("asr_silence_ms", 320, 2000), ("tts_prebuffer_ms", 0, 1000)):
        value = data.get(name)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"Invalid {name}: expected integer from {low} to {high}")
    if not isinstance(data.get("llm_model"), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", data["llm_model"]):
        raise ValueError("llm_model must be a directory name inside models/")
    if type(data.get("llm_do_sample")) is not bool:
        raise ValueError("llm_do_sample must be a boolean")
    if data["llm_output_tokens"] >= data["llm_max_context"]:
        raise ValueError("llm_output_tokens must leave room for input within llm_max_context")
    for name in ("amd_installation_path", "amd_environment", "asr_python"):
        if not isinstance(data.get(name), str):
            raise ValueError(f"{name} must be a path string")
    if not data["asr_python"]:
        raise ValueError("asr_python must not be empty")
    return data


def prepare_directories():
    for name in ("logs", "work", "cache"):
        (ROOT / name).mkdir(exist_ok=True)


def asr_python(config):
    path = Path(os.environ.get("RIG_ASR_PYTHON", config["asr_python"]))
    return path if path.is_absolute() else ROOT / path
