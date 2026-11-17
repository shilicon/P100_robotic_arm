"""Check local prerequisites without loading the LLM or contacting a robot."""
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def main():
    from settings import load_config, asr_python
    failures = []
    try:
        config = load_config()
    except (ValueError, OSError) as error:
        print("Configuration: " + str(error))
        return 1
    if os.name != "nt" or sys.version_info[:2] != (3, 12):
        failures.append("Live backend requires Windows and AMD Python 3.12.")
    import bootstrap
    for package, expected in (("onnxruntime-vitisai", "1.27.0"), ("onnxruntime-genai-directml-ryzenai", "0.14.0")):
        try:
            actual = importlib.metadata.version(package)
            if actual != expected:
                failures.append(f"{package}: expected {expected}, found {actual}")
        except importlib.metadata.PackageNotFoundError:
            failures.append("Missing AMD package: " + package)
    try:
        import onnxruntime
        import onnxruntime_genai
        print("ORT providers: " + ", ".join(onnxruntime.get_available_providers()))
    except (ImportError, OSError) as error:
        failures.append("AMD native runtime cannot load: " + str(error))
    interpreter = asr_python(config)
    if not interpreter.is_file():
        failures.append("CPU ASR Python is missing; run setup.ps1.")
    else:
        # Use the same environment isolation as the live worker.
        from asr_proxy import cpu_environment
        result = subprocess.run([str(interpreter), "-c", "import sherpa_onnx, numpy"], env=cpu_environment(),
                                capture_output=True, text=True, timeout=30)
        if result.returncode:
            failures.append("CPU ASR dependencies cannot load.")
    manifest = json.loads((ROOT / "manifests/models.json").read_text())
    missing = [f["path"] for m in manifest["models"] for f in m["files"] if not (ROOT / "models" / f["path"]).is_file()]
    if missing:
        failures.append(f"Missing {len(missing)} model files. Use scripts/models.py download/verify.")
    if config["llm_model"] != "qwen3-8b-npu-4k":
        failures.append("Custom model is outside the pinned manifest; validate its runtime and context separately.")
    if os.name == "nt":
        try:
            import win32com.client
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            voices = speaker.GetVoices()
            if not any("Huihui" in voices.Item(i).GetDescription() for i in range(voices.Count)):
                failures.append("Microsoft Huihui Chinese SAPI voice is missing.")
        except Exception:
            failures.append("Windows SAPI voice enumeration failed.")
    for failure in failures:
        print("CHECK: " + failure)
    print("File presence and runtime imports cannot prove NPU execution. Hardware inference remains a separate check.")
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
