import concurrent.futures
import json
import time
from pathlib import Path
import sys
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from settings import load_config, prepare_directories
prepare_directories()
cfg = load_config()
headers = {'Authorization': 'Bearer ' + cfg['api_key']}
prompt = (ROOT / 'prompts/robot.txt').read_text(encoding='utf-8')
tools = json.loads((ROOT / 'tests/robot-tools.json').read_text(encoding='utf-8'))
def heavy_request():
    with httpx.Client(timeout=90, trust_env=False) as client:
        response = client.post(f"http://127.0.0.1:{cfg['port']}/v1/chat/completions", headers=headers,
            json={'tools': tools, 'max_tokens': 120, 'messages': [
                {'role': 'system', 'content': prompt}, {'role': 'user', 'content': '你能做什么？'}]})
        response.raise_for_status()
        return response.json()['choices'][0]['message']
latencies = []
start = time.perf_counter()
with concurrent.futures.ThreadPoolExecutor() as pool:
    job = pool.submit(heavy_request)
    with httpx.Client(timeout=2, trust_env=False) as client:
        while not job.done():
            before = time.perf_counter()
            response = client.get(f"http://127.0.0.1:{cfg['port']}/health")
            response.raise_for_status()
            latencies.append(time.perf_counter()-before)
            time.sleep(0.25)
    message = job.result()
assert message.get('content') and not message.get('tool_calls'), message
assert max(latencies) < 1, latencies
report = {'passed': True, 'reply': message['content'], 'seconds': round(time.perf_counter()-start, 3),
          'health_max_seconds': round(max(latencies), 3), 'health_checks': len(latencies)}
(ROOT / 'logs/responsiveness.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
