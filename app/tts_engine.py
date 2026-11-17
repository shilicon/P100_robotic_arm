import io
import asyncio
import tempfile
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


_speaker = None


def _initialize():
    global _speaker
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    _speaker = win32com.client.Dispatch("SAPI.SpVoice")
    voices = _speaker.GetVoices()
    for index in range(voices.Count):
        voice = voices.Item(index)
        if "Huihui" in voice.GetDescription():
            _speaker.Voice = voice
            break
    else:
        raise RuntimeError("Microsoft Huihui Chinese voice is not installed")
    _speaker.Rate = 1
    _speaker.Volume = 100


_executor = ThreadPoolExecutor(max_workers=1, initializer=_initialize, thread_name_prefix='sapi')


def _synthesize(text: str) -> bytes:
    """Run all SAPI calls on the persistent COM thread."""
    if not isinstance(text, str):
        raise ValueError('Speech text must be a string')
    if not text.strip():
        return b""
    if len(text) > 4000:
        raise ValueError("Speech text is too long")
    import win32com.client
    path = None
    stream = None
    try:
        from bootstrap import ROOT
        with tempfile.NamedTemporaryFile(suffix=".wav", dir=ROOT / "work", delete=False) as f:
            path = Path(f.name)
        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        stream.Format.Type = 18  # SAFT16kHz16BitMono
        stream.Open(str(path), 3, False)
        _speaker.AudioOutputStream = stream
        _speaker.Speak(text, 16)  # SVSFIsNotXML: literal text, never load XML audio.
        stream.Close()
        stream = None
        with wave.open(str(path), "rb") as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 16000):
                raise RuntimeError("Unexpected Windows TTS audio format")
            return wav.readframes(wav.getnframes())
    finally:
        if stream is not None:
            stream.Close()
        if path is not None:
            path.unlink(missing_ok=True)


def synthesize(text: str) -> bytes:
    return _executor.submit(_synthesize, text).result()


async def synthesize_async(text: str) -> bytes:
    # Cancellation also removes queued work that has not started yet.
    return await asyncio.wrap_future(_executor.submit(_synthesize, text))


def close():
    def dispose():
        import pythoncom
        global _speaker
        _speaker = None
        pythoncom.CoUninitialize()
    _executor.submit(dispose).result()
    _executor.shutdown(wait=True, cancel_futures=True)


def as_wav(pcm: bytes) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm)
    return output.getvalue()
