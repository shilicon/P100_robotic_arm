"""Verify long-sentence streaming and model-request cancellation without robot calls."""
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
tools = json.loads((ROOT / 'tests/robot-tools.json').read_text(encoding='utf-8'))
prompt = (ROOT / 'prompts/robot.txt').read_text(encoding='utf-8')
result = {'tools_executed': False}
with httpx.Client(base_url=f"http://127.0.0.1:{cfg['port']}", timeout=90, trust_env=False,
                  headers={'Authorization': 'Bearer ' + cfg['api_key']}) as client:
    start = time.perf_counter()
    with client.stream('POST', '/v1/chat/completions', json={'tools': tools, 'stream': True,
        'max_tokens': 160, 'messages': [{'role': 'system', 'content': prompt},
        {'role': 'user', 'content': '不要执行任何动作，只告诉我你能做什么'}]}) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith('data: ') or line == 'data: [DONE]':
                continue
            packet = json.loads(line[6:])
            assert 'error' not in packet, packet
            delta = packet['choices'][0]['delta']
            assert not delta.get('tool_calls')
            if delta.get('content'):
                result['first_segment_seconds'] = round(time.perf_counter() - start, 4)
                result['segment'] = delta['content']
                assert '\n' in delta['content'], 'Long list should flush at a natural pause before final period'
                break  # Close SSE while the model still has more to generate.
    start = time.perf_counter()
    response = client.post('/v1/chat/completions', json={'tools': tools, 'max_tokens': 40,
        'messages': [{'role': 'system', 'content': prompt}, {'role': 'user', 'content': '请只回复两个字：收到。'}]})
    response.raise_for_status()
    message = response.json()['choices'][0]['message']
    assert '收到' in message['content'] and not message.get('tool_calls'), message
    result['next_reply'] = message['content']
    result['next_request_seconds'] = round(time.perf_counter() - start, 4)
    result['passed'] = True
(ROOT / 'logs/pipeline-streaming.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
