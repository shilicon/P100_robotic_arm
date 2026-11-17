"""Local Silero VAD, 16 kHz / 512 samples per inference, CPU only."""
from pathlib import Path
import numpy as np
import onnxruntime as ort

ROOT = Path(__file__).resolve().parents[1]

class SpeechVad:
    frame_bytes = 1024
    frame_ms = 32
    def __init__(self):
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(ROOT / 'models/silero_vad.onnx'), options,
                                           providers=['CPUExecutionProvider'])
        self.reset()

    def reset(self):
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.context = np.zeros((1, 64), dtype=np.float32)

    def is_speech(self, frame, sample_rate=16000):
        samples = np.frombuffer(frame, dtype='<i2').astype(np.float32)[None, :] / 32768
        audio = np.concatenate((self.context, samples), axis=1)
        probability, self.state = self.session.run(None, {'input': audio, 'state': self.state,
                                                         'sr': np.array(16000, dtype=np.int64)})
        self.context = audio[:, -64:].copy()
        return float(probability[0, 0]) >= 0.5
