"""Combine received silence and gated network silence on one endpoint clock."""
from collections import deque


class EndpointDetector:
    def __init__(self, vad, silence_ms=800):
        self.vad = vad
        self.silence_ms = silence_ms
        self.pre = deque(maxlen=10)
        self.recent = deque(maxlen=5)
        self.buffer = bytearray()
        self.utterance = bytearray()
        self.active = False
        self.silent_frames = 0
        self.last_audio_at = 0.0

    def clear(self):
        self.pre.clear()
        self.recent.clear()
        self.buffer.clear()
        self.utterance.clear()
        self.active = False
        self.silent_frames = 0
        self.vad.reset()

    def deadline(self):
        if not self.active:
            return None
        remaining = max(0, self.silence_ms - self.silent_frames * self.vad.frame_ms)
        return self.last_audio_at + remaining / 1000

    def finish(self, reason, now, partial=False):
        if not self.active:
            return []
        if partial:
            self.utterance.extend(self.buffer)
            self.buffer.clear()
        pcm = bytes(self.utterance)
        silence = self.silent_frames * self.vad.frame_ms + max(0, now - self.last_audio_at) * 1000
        self.active = False
        self.utterance.clear()
        self.pre.clear()
        self.recent.clear()
        self.silent_frames = 0
        return [{'type': 'speech_stopped', 'pcm': pcm, 'reason': reason, 'silence_ms': round(silence, 1)}]

    def poll(self, now):
        deadline = self.deadline()
        if deadline is not None and now >= deadline:
            return self.finish('silence', now, partial=True)
        return []

    def feed(self, pcm, now):
        events = self.poll(now)
        if not pcm:
            return events
        self.last_audio_at = now
        self.buffer.extend(pcm)
        while len(self.buffer) >= self.vad.frame_bytes:
            frame = bytes(self.buffer[:self.vad.frame_bytes])
            del self.buffer[:self.vad.frame_bytes]
            voiced = self.vad.is_speech(frame, 16000)
            if not self.active:
                self.pre.append(frame)
                self.recent.append(voiced)
                if sum(self.recent) >= 3:
                    self.active = True
                    self.silent_frames = 0
                    self.utterance.extend(b''.join(self.pre))
                    self.pre.clear()
                    events.append({'type': 'speech_started'})
            else:
                self.utterance.extend(frame)
                self.silent_frames = 0 if voiced else self.silent_frames + 1
                if self.silent_frames * self.vad.frame_ms >= self.silence_ms:
                    events.extend(self.finish('silence', now))
                elif len(self.utterance) >= 32000 * 25:
                    events.extend(self.finish('max-duration', now))
        return events
