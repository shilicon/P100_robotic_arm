"""Release complete speech sentences while keeping protocol fragments private."""
import re


class SpeechStream:
    def __init__(self):
        self.pending = ''

    def feed(self, text, final=False):
        self.pending += text
        # Hold complete sentences rather than arbitrary tokens. A partial tag,
        # raw JSON or code cannot reach TTS across a token boundary.
        if any(marker in self.pending for marker in ('<', '>', '{', '}', '```')):
            raise ValueError('Model returned non-speech protocol/code content')
        if re.search(r'"(?:name|arguments|parameters)"\s*:', self.pending):
            raise ValueError('Model returned raw tool JSON')
        output = []
        while match := re.search(r'[。！？；…\n]', self.pending):
            sentence, self.pending = self.pending[:match.end()], self.pending[match.end():]
            if sentence.strip():
                output.append({'content': sentence})
        # A model may ignore the short-first-sentence instruction and generate
        # a long enumeration. The existing firmware flushes on newline, so use
        # a natural pause rather than holding the entire list until its period.
        while len(self.pending) >= 36:
            pauses = [m.end() for m in re.finditer(r'[，,、：:]', self.pending[:48]) if m.end() >= 16]
            if not pauses:
                break
            end = pauses[-1]
            output.append({'content': self.pending[:end] + '\n'})
            self.pending = self.pending[end:]
        if final and self.pending:
            if self.pending.strip():
                output.append({'content': self.pending})
            self.pending = ''
        return output
