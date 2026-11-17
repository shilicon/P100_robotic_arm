"""Create private credentials; optionally generate a local-only firmware header."""
import argparse
import ipaddress
import json
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from settings import load_config, config_path, prepare_directories


def write_private(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        output.write(text)


def firmware_header(config):
    address = ipaddress.IPv4Address(config["lan_host"])
    return ("#pragma once\n// Generated private configuration. Never publish this file or its firmware binary.\n"
            "#define RIG_LOCAL_SERVICES_ENABLED 1\n"
            f'#define RIG_LOCAL_SERVICE_HOST "{address}:{config["port"]}"\n'
            f'#define RIG_LOCAL_SERVICE_TOKEN "{config["api_key"]}"\n'
            f'#define RIG_MCP_TOKEN "{config["robot_api_key"]}"\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lan-host", help="PC IPv4 address reachable by the robot")
    parser.add_argument("--listen-lan", action="store_true")
    parser.add_argument("--amd-installation", default=os.environ.get("RYZEN_AI_INSTALLATION_PATH", ""))
    parser.add_argument("--amd-environment", default=os.environ.get("CONDA_PREFIX", ""))
    parser.add_argument("--firmware-dir", type=Path, help="Private vendor source directory, optional")
    args = parser.parse_args()
    path = config_path()
    if not path.exists():
        if not args.lan_host:
            parser.error("--lan-host is required for initial setup")
        ipaddress.IPv4Address(args.lan_host)
        config = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
        config.update(lan_host=args.lan_host, host="0.0.0.0" if args.listen_lan else "127.0.0.1",
                      api_key=secrets.token_urlsafe(32), robot_api_key=secrets.token_urlsafe(32),
                      amd_installation_path=args.amd_installation, amd_environment=args.amd_environment)
        write_private(path, json.dumps(config, ensure_ascii=False, indent=2) + "\n")
        print("Created private configuration with separate service and device tokens.")
    else:
        print("Existing configuration preserved; command-line configuration options were not applied.")
    config = load_config()
    prepare_directories()
    if args.firmware_dir:
        path = args.firmware_dir / "main/cloud_api/local_service_config.h"
        if path.exists():
            if path.read_text(encoding="utf-8") != firmware_header(config):
                raise ValueError("Firmware header differs. Back it up and remove it before regenerating.")
            print("Firmware header already matches.")
        else:
            write_private(path, firmware_header(config))
            print("Created private firmware header. Rebuilding and flashing remain manual steps.")


if __name__ == "__main__":
    main()
