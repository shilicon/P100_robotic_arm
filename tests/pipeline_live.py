"""Online text-only semantic checks. Tool calls are inspected, never executed."""
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
rows = []


def check(client, name, messages, expected=None):
    start = time.perf_counter()
    response = client.post('/v1/chat/completions', json={'tools': tools, 'max_tokens': 160,
        'messages': [{'role': 'system', 'content': prompt}] + messages})
    response.raise_for_status()
    message = response.json()['choices'][0]['message']
    functions = [call['function'] for call in message.get('tool_calls', [])]
    actual = [(f['name'], json.loads(f['arguments'])) for f in functions]
    passed = actual == expected if expected is not None else not actual
    row = {'case': name, 'message': message, 'route': response.headers.get('x-local-route'),
           'input_tokens': response.headers.get('x-local-input-tokens'),
           'seconds': round(time.perf_counter()-start, 4), 'passed': passed}
    rows.append(row)
    (ROOT / 'logs/pipeline-live.json').write_text(json.dumps(
        {'tools_executed': False, 'cases': rows}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(row, ensure_ascii=False), flush=True)


with httpx.Client(base_url=f"http://127.0.0.1:{cfg['port']}", timeout=90, trust_env=False,
                  headers={'Authorization': 'Bearer ' + cfg['api_key']}) as client:
    for name, question, expected in [
        ('shy', '请表演害羞', [('self_arm_shy', {})]),
        ('forward1', '把头往前移动一厘米', [('self_arm_x', {'x': 1})]),
        ('up2', '把头往上移动两厘米', [('self_arm_z', {'z': 2})]),
        ('negation', '不要执行任何动作，只告诉我你能做什么', []),
        ('range', '向右转90度', []),
    ]:
        check(client, name, [{'role': 'user', 'content': question}], expected)
    call = {'id': 'test_accepted', 'type': 'function',
            'function': {'name': 'self_arm_teach_start', 'arguments': '{}'}}
    check(client, 'accepted_result', [
        {'role': 'user', 'content': '开始示教录制'},
        {'role': 'assistant', 'content': None, 'tool_calls': [call]},
        {'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps({'isError': False,
            'content': [{'type': 'text', 'text': '已接受（accepted）：开始示教准备；请等待归位并放松舵机后再拖动。尚未完成，请勿重复提交。'}]}, ensure_ascii=False)}], [])
    call = {'id': 'test_volume', 'type': 'function',
            'function': {'name': 'self_get_device_status', 'arguments': '{}'}}
    check(client, 'status_prerequisite', [
        {'role': 'user', 'content': '请把音量调到30'},
        {'role': 'assistant', 'content': None, 'tool_calls': [call]},
        {'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps({'isError': False,
            'content': [{'type': 'text', 'text': '{"audio_speaker":{"volume":50}}'}]})}],
        [('self_audio_speaker_set_volume', {'volume': 30})])
    history = []
    for index in range(8):
        history += [{'role': 'user', 'content': ('这是以前的聊天内容。' * 200) + str(index)},
                    {'role': 'assistant', 'content': '好的。'}]
    check(client, 'long_history', history + [{'role': 'user', 'content': '请用一句话说你好。'}], [])
print('Passed', sum(r['passed'] for r in rows), '/', len(rows), '(tool format/arguments and no-action checks; inspect response semantics separately)')
