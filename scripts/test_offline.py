"""Run tests without model files, private config, AMD libraries, or a robot."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    for args in (["tests/pipeline.py"], ["tests/tool_parser.py"],
                 ["-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"]):
        subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
