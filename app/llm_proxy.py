import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class LlmProxy:
    def __init__(self, config):
        self.lock = threading.Lock()
        self.lines = queue.Queue()
        self.error_log = (ROOT / 'logs/llm-worker.log').open('a', encoding='utf-8')
        self.process = subprocess.Popen(
            [sys.executable, '-u', str(ROOT / 'app/llm_worker.py')],
            cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.error_log,
            text=True, encoding='utf-8', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        def read_lines():
            for line in self.process.stdout:
                try:
                    self.lines.put(json.loads(line))
                except ValueError:
                    self.error_log.write(line)
                    self.error_log.flush()
            self.lines.put({'kind': 'error', 'message': 'NPU worker exited'})
        threading.Thread(target=read_lines, daemon=True).start()
        first = self.lines.get(timeout=90)
        if not first.get('ready'):
            self.close()
            raise RuntimeError(first.get('message', 'NPU worker failed to start'))

    def send(self, data):
        self.process.stdin.write(json.dumps(data, ensure_ascii=False) + '\n')
        self.process.stdin.flush()

    def encode_request(self, body):
        with self.lock:
            identity = time.time_ns()
            self.send({'id': identity, 'kind': 'encode', 'body': body})
            reply = self.lines.get(timeout=90)
            if reply.get('kind') == 'error':
                raise ValueError(reply['message'])
            if reply.get('id') != identity or reply.get('kind') != 'encoded':
                raise RuntimeError('Unexpected NPU worker response')
            return reply['tokens'], reply['limit']

    def chunks(self, tokens, output_limit, stop):
        with self.lock:
            identity = time.time_ns()
            self.send({'id': identity, 'kind': 'generate', 'tokens': tokens, 'limit': output_limit})
            cancelled = False
            deadline = time.monotonic() + 180
            while True:
                if stop.is_set() and not cancelled:
                    self.send({'id': identity, 'kind': 'cancel'})
                    cancelled = True
                try:
                    reply = self.lines.get(timeout=0.1)
                except queue.Empty:
                    if time.monotonic() > deadline:
                        self.process.kill()
                        raise TimeoutError('NPU request timed out; restart the service')
                    continue
                if reply.get('kind') == 'error':
                    raise RuntimeError(reply['message'])
                if reply.get('id') != identity:
                    raise RuntimeError('Unexpected NPU request identity')
                if reply['kind'] == 'done':
                    break
                if not cancelled:
                    yield reply['text']

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.error_log.close()
