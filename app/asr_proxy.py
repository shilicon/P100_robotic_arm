import base64
import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from settings import load_config, asr_python

ROOT = Path(__file__).resolve().parents[1]


def cpu_environment():
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    config = load_config()
    roots = [config.get("amd_installation_path", ""), config.get("amd_environment", ""),
             env.get("RYZEN_AI_INSTALLATION_PATH", ""), env.get("CONDA_PREFIX", "")]
    roots = [os.path.normcase(os.path.abspath(p)) for p in roots if p]
    def keep(path):
        normalized = os.path.normcase(os.path.abspath(path))
        return ("ryzenai" not in path.lower() and "ryzen-ai" not in path.lower()
                and not any(normalized == root or normalized.startswith(root + os.sep) for root in roots))
    env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep) if p and keep(p))
    for key in ("PYTHONPATH", "PYTHONHOME", "RYZEN_AI_INSTALLATION_PATH", "CONDA_PREFIX"):
        env.pop(key, None)
    return env


class AsrProxy:
    def __init__(self):
        self.lock = threading.Lock()
        self.lines = queue.Queue()
        self.error_log = (ROOT / "logs" / "asr-worker.log").open("a", encoding="utf-8")
        env = cpu_environment()
        self.process = subprocess.Popen(
            [str(asr_python(load_config())), "-u", str(ROOT / "app" / "asr_worker.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.error_log,
            text=True, encoding="utf-8", env=env, cwd=ROOT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

        def read_lines():
            for line in self.process.stdout:
                try:
                    self.lines.put(json.loads(line))
                except ValueError:
                    self.error_log.write(line)
                    self.error_log.flush()
            self.lines.put({"error": "ASR worker exited"})
        threading.Thread(target=read_lines, daemon=True).start()
        first = self.lines.get(timeout=60)
        if not first.get("ready"):
            self.close()
            raise RuntimeError(first.get("error", "ASR failed to start"))

    def transcribe(self, pcm):
        if not pcm or len(pcm) % 2 or len(pcm) > 32000 * 30:
            raise ValueError("Expected 16 kHz mono PCM, up to 30 seconds")
        with self.lock:
            identity = time.time_ns()
            payload = {"id": identity, "pcm": base64.b64encode(pcm).decode("ascii")}
            self.process.stdin.write(json.dumps(payload) + "\n")
            self.process.stdin.flush()
            response = self.lines.get(timeout=60)
            if response.get("id") != identity or "error" in response:
                raise RuntimeError(response.get("error", "Unexpected ASR response"))
            return response["text"]

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.error_log.close()
