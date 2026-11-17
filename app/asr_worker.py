"""CPU ASR process: intentionally does not load AMD's ONNX Runtime DLL."""
import base64
import json
import sys
from sensevoice_engine import SenseVoiceAsr

engine = SenseVoiceAsr()
print(json.dumps({"ready": True}), flush=True)
for line in sys.stdin:
    try:
        item = json.loads(line)
        text = engine.transcribe(base64.b64decode(item["pcm"]))
        print(json.dumps({"id": item["id"], "text": text}, ensure_ascii=False), flush=True)
    except Exception as error:
        print(json.dumps({"error": str(error)}), flush=True)
