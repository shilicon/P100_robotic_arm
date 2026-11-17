"""Own native NPU inference in a separate process so HTTP/WS stays responsive."""
import bootstrap
import json
import queue
import sys
import threading
from llm_engine import QwenLlm
from settings import load_config

jobs = queue.Queue()
stops = {}
write_lock = threading.Lock()

def emit(data):
    with write_lock:
        print(json.dumps(data, ensure_ascii=False), flush=True)

def reader():
    for line in sys.stdin:
        data = json.loads(line)
        if data.get('kind') == 'cancel':
            if data['id'] in stops:
                stops[data['id']].set()
        else:
            stops[data['id']] = threading.Event()
            jobs.put(data)
    for stop in stops.values():
        stop.set()
    jobs.put(None)

llm = QwenLlm(load_config())
threading.Thread(target=reader, daemon=True).start()
emit({'ready': True})
while True:
    job = jobs.get()
    if job is None:
        break
    identity = job['id']
    try:
        if job['kind'] == 'encode':
            tokens, limit = llm.encode_request(job['body'])
            emit({'id': identity, 'kind': 'encoded', 'tokens': [int(t) for t in tokens], 'limit': limit})
        elif job['kind'] == 'generate':
            for piece in llm.chunks(job['tokens'], job['limit'], stops[identity]):
                emit({'id': identity, 'kind': 'chunk', 'text': piece})
            emit({'id': identity, 'kind': 'done'})
    except Exception as error:
        emit({'id': identity, 'kind': 'error', 'message': str(error)})
    finally:
        stops.pop(identity, None)
