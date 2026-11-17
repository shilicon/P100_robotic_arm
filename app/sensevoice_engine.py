import threading
import numpy as np
import sherpa_onnx
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


class SenseVoiceAsr:
    def __init__(self):
        self.device = "cpu"
        self.lock = threading.Lock()
        folder = ROOT / "models" / "sensevoice"
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(folder / "model.int8.onnx"), tokens=str(folder / "tokens.txt"),
            num_threads=4, use_itn=True, language="zh", provider="cpu", debug=False)

    def transcribe(self, pcm):
        if len(pcm) % 2 or not pcm or len(pcm) > 32000 * 30:
            raise ValueError("Expected 16 kHz mono PCM, up to 30 seconds")
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        with self.lock:
            stream = self.recognizer.create_stream()
            stream.accept_waveform(16000, samples)
            self.recognizer.decode_stream(stream)
            return stream.result.text.strip()
