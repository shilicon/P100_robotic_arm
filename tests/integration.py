"""Exercise the local services over HTTP/WS; never sends robot actions."""
import asyncio
import base64
import io
import json
import time
import wave
from pathlib import Path
import sys
import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from settings import load_config, prepare_directories
prepare_directories()
CONFIG = load_config()
HEADERS = {'Authorization': 'Bearer ' + CONFIG['api_key']}
BASE = f"http://127.0.0.1:{CONFIG['port']}"
RESULT = {}
TTS_SENTENCES = ['本地语音服务已启动。', '第二句话的结尾也要完整播放。']


async def main():
    async with httpx.AsyncClient(base_url=BASE, headers=HEADERS, timeout=120, trust_env=False) as client:
        response = await client.get('/health')
        response.raise_for_status()
        assert response.json()['ready']
        RESULT['health'] = response.json()
        assert (await client.get('/v1/models', headers={'Authorization': ''})).status_code == 401
        assert (await client.post('/local/asr', content=b'x')).status_code == 400
        response = await client.post('/v1/audio/speech', json={'input': '你好，请告诉我现在语音服务是否在本机运行。'})
        response.raise_for_status()
        with wave.open(io.BytesIO(response.content), 'rb') as wav:
            assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2)
            pcm = wav.readframes(wav.getnframes())
        (ROOT / 'logs' / 'http-tts.wav').write_bytes(response.content)
        response = await client.post('/local/asr', content=pcm)
        response.raise_for_status()
        RESULT['http_asr'] = response.json()
        assert '语音服务' in response.json()['text'] and '本机' in response.json()['text']

        start = time.perf_counter()
        content = ''
        done = False
        async with client.stream('POST', '/v1/chat/completions', json={
            'model': CONFIG['llm_model'], 'stream': True, 'max_tokens': 80,
            'messages': [{'role': 'user', 'content': '请用一句中文介绍你能做什么。'}]
        }) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line == 'data: [DONE]':
                    done = True
                elif line.startswith('data: '):
                    data = json.loads(line[6:])
                    assert 'error' not in data, data
                    content += data['choices'][0]['delta'].get('content', '')
        assert content and done
        RESULT['llm_stream'] = {'text': content, 'seconds': round(time.perf_counter()-start, 3)}

        # A fake tool validates generation/serialization only; nothing executes it.
        tools = [{'type': 'function', 'function': {'name': 'get_test_temperature',
            'description': '获取测试房间温度', 'parameters': {'type': 'object',
            'properties': {'room': {'type': 'string'}}, 'required': ['room']}}}]
        response = await client.post('/v1/chat/completions', json={
            'tools': tools, 'max_tokens': 120,
            'messages': [{'role': 'system', 'content': '你必须调用提供的工具获取温度，不要猜测。'},
                         {'role': 'user', 'content': '请获取实验室的温度。'}]})
        response.raise_for_status()
        data = response.json()['choices'][0]
        calls = data['message'].get('tool_calls', [])
        assert data['finish_reason'] == 'tool_calls' and len(calls) == 1, data
        assert calls[0]['function']['name'] == 'get_test_temperature'
        assert isinstance(json.loads(calls[0]['function']['arguments'])['room'], str)
        RESULT['tool_call'] = calls[0]['function']
        expected_audio = bytearray()
        for text in TTS_SENTENCES:
            response = await client.post('/v1/audio/speech', json={'input': text, 'response_format': 'pcm'})
            response.raise_for_status()
            expected_audio.extend(response.content)

    async with websockets.connect(f"ws://127.0.0.1:{CONFIG['port']}/api-ws/v1/realtime", additional_headers=HEADERS, proxy=None) as ws:
        await ws.send(json.dumps({'type': 'session.update', 'session': {'sample_rate': 16000,
            'turn_detection': {'silence_duration_ms': 800}}}))
        assert json.loads(await ws.recv())['type'] == 'session.created'
        for offset in range(0, len(pcm), 1920):
            await ws.send(json.dumps({'type': 'input_audio_buffer.append',
                'audio': base64.b64encode(pcm[offset:offset+1920]).decode()}))
        # Real firmware drops gated quiet frames; do not manufacture trailing silence.
        events = []
        while True:
            event = json.loads(await asyncio.wait_for(ws.recv(), 5))
            events.append(event['type'])
            assert event['type'] != 'error', event
            if event['type'] == 'conversation.item.input_audio_transcription.completed':
                RESULT['websocket_asr'] = {'text': event['transcript'], 'events': events}
                assert '语音服务' in event['transcript']
                assert events[:2] == ['input_audio_buffer.speech_started', 'input_audio_buffer.speech_stopped']
                break

    async with websockets.connect(f"ws://127.0.0.1:{CONFIG['port']}/api-ws/v1/inference/", additional_headers=HEADERS, proxy=None) as ws:
        await ws.send(json.dumps({'header': {'action': 'run-task', 'task_id': 'integration-test'}, 'payload': {}}))
        assert json.loads(await ws.recv())['header']['event'] == 'task-started'
        for text in TTS_SENTENCES:
            await ws.send(json.dumps({'header': {'action': 'continue-task'}, 'payload': {'input': {'text': text}}}))
        await ws.send(json.dumps({'header': {'action': 'finish-task'}, 'payload': {}}))
        audio = bytearray()
        events = []
        while True:
            message = await asyncio.wait_for(ws.recv(), 20)
            if isinstance(message, bytes):
                audio.extend(message)
            else:
                event = json.loads(message)['header']['event']
                events.append(event)
                assert event != 'task-failed', message
                if event == 'task-finished':
                    break
        assert len(audio) > 32000 and len(audio) % 2 == 0
        assert audio == expected_audio, 'WebSocket PCM must retain every byte, including both sentence tails'
        assert events == ['result-generated', 'result-generated', 'task-finished'], events
        RESULT['websocket_tts'] = {'audio_seconds': len(audio)/32000, 'events': events, 'byte_exact': True}
    RESULT['passed'] = True
    (ROOT / 'logs' / 'integration-results.json').write_text(json.dumps(RESULT, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(RESULT, ensure_ascii=False, indent=2))


asyncio.run(main())
