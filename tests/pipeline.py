"""Deterministic pipeline regression tests; no model inference or robot connection."""
import asyncio
import base64
import json
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
import bootstrap
from conversation_policy import prepare_request, BUILTIN, validate_arguments
from endpointing import EndpointDetector
from history_context import fit_history
from speech_stream import SpeechStream
from tts_pipeline import deliver, split_text

TOOLS = json.loads((ROOT / 'tests/robot-tools.json').read_text(encoding='utf-8'))


def request(text):
    return prepare_request({'tools': TOOLS, 'messages': [
        {'role': 'system', 'content': '自定义名字：小鹿。\n' + BUILTIN + '\n请用中文。'},
        {'role': 'user', 'content': text}]})


class FakeVad:
    frame_bytes = 1024
    frame_ms = 32
    def is_speech(self, frame, sample_rate):
        return frame[0] != 0
    def reset(self):
        pass


class PolicyTests(unittest.TestCase):
    def test_exact_commands_and_range(self):
        for question, name, arguments in [
            ('向右转20度。', 'yaw', {'yaw': -20}), ('请你向左转二十度', 'yaw', {'yaw': 20}),
            ('抬头十度', 'pitch', {'pitch': -10}), ('向右歪头10度', 'roll', {'roll': -10}),
            ('向左平移两厘米', 'y', {'y': 2}), ('关闭空闲微动', 'idle_motion', {'enable': 0}),
            ('请表演害羞', 'shy', {}), ('来个鞠躬动作', 'bow', {}),
            ('把头往前移动一厘米', 'x', {'x': 1}), ('把头往上移动两厘米', 'z', {'z': 2}),
            ('结束示教并保存，不要回放', 'teach_stop', {}), ('别动了，停止正在做的动作', 'stop', {})]:
            body, events = request(question)
            self.assertEqual(body['_local_route'], 'exact-command', question)
            function = events[0]['tool_calls'][0]['function']
            self.assertEqual(function['name'], 'self_arm_' + name)
            self.assertEqual(json.loads(function['arguments']), arguments)
        body, events = request('向右转90度')
        self.assertEqual(body['_local_route'], 'range-clarification')
        self.assertNotIn('tool_calls', events[0])
        self.assertNotIn('yaw', events[0]['content'])

    def test_non_commands_and_preserved_customization(self):
        for question in ['不要向右转20度', '如果向右转20度会怎样？', '朗读“向右转20度”',
                         '解释一下鞠躬的意思', '你能做什么？', '你好', '请讲一个故事']:
            body, events = request(question)
            self.assertEqual(body['_local_route'], 'chat', question)
            self.assertEqual(body['tools'], [])
            self.assertIsNone(events)
            self.assertIn('自定义名字：小鹿', body['messages'][0]['content'])
            self.assertIn('请用中文', body['messages'][0]['content'])
        for question in ['先向右转20度再鞠躬', '向右转20度？', '我想看看你害羞的样子']:
            body, events = request(question)
            self.assertIsNone(events)
            self.assertEqual(len(body['tools']), 33)

    def test_schema(self):
        schema = {'type': 'object', 'properties': {'yaw': {'type': 'integer', 'minimum': -60, 'maximum': 60}}, 'required': ['yaw']}
        for invalid in [{'yaw': True}, {'yaw': 1.5}, {'yaw': '20'}, {'yaw': 61}, {}, {'yaw': 20, 'x': 1}]:
            with self.assertRaises(ValueError):
                validate_arguments(invalid, schema)
        validate_arguments({'yaw': -60}, schema)

    def test_history_keeps_latest_tool_exchange(self):
        messages = [{'role': 'system', 'content': 'custom'}, {'role': 'user', 'content': 'old'},
                    {'role': 'assistant', 'tool_calls': [{'id': 'old'}]}, {'role': 'tool', 'tool_call_id': 'old'},
                    {'role': 'user', 'content': 'latest'}, {'role': 'assistant', 'tool_calls': [{'id': 'new'}]},
                    {'role': 'tool', 'tool_call_id': 'new'}]
        observed = []
        def encode(ms):
            observed.append(ms)
            return [0] * len(ms)
        fit_history(messages, encode, 4)
        self.assertEqual(observed[-1], [messages[0]] + messages[4:])
        with self.assertRaises(ValueError):
            fit_history(messages, encode, 3)

    def test_speech_stream_splits_and_malformed(self):
        text = '第一句。第二句！末尾'
        for split in range(len(text) + 1):
            stream = SpeechStream()
            events = stream.feed(text[:split]) + stream.feed(text[split:]) + stream.feed('', final=True)
            self.assertEqual(''.join(e['content'] for e in events), text)
        for text in ['<think>秘密</think>回答。', '{"name":"动作"}', '```json\n', '"arguments":123']:
            for split in range(len(text) + 1):
                stream = SpeechStream()
                with self.assertRaises(ValueError):
                    stream.feed(text[:split]); stream.feed(text[split:]); stream.feed('', final=True)

    def test_long_sentence_can_start_before_period(self):
        text = '我可以做这些动作：鞠躬、点头、摇头、伸懒腰、害羞、撒娇、道歉、装死、摇尾巴、左右旋转。'
        stream, events = SpeechStream(), []
        for char in text[:-1]:
            events.extend(stream.feed(char))
        self.assertTrue(events, 'A long enumeration should start before its final period')
        self.assertTrue(events[0]['content'].endswith('\n'))
        events.extend(stream.feed(text[-1], final=True))
        self.assertEqual(''.join(e['content'] for e in events).replace('\n', ''), text)


class EndpointTests(unittest.TestCase):
    def active(self):
        detector = EndpointDetector(FakeVad(), silence_ms=640)
        self.assertEqual(detector.feed(b'\1' * 3072, 1)[0]['type'], 'speech_started')
        return detector

    def test_quiet_and_gate_share_clock(self):
        detector = self.active()
        for i in range(10):
            detector.feed(b'\0' * 1024, 1 + (i + 1) * .032)
        self.assertAlmostEqual(detector.deadline(), 1.64)
        self.assertFalse(detector.poll(1.63))
        stopped = detector.poll(1.641)
        self.assertEqual(stopped[0]['type'], 'speech_stopped')
        self.assertFalse(detector.poll(3))

    def test_continuous_quiet_pause_commit_and_clear(self):
        detector = self.active()
        events = detector.feed(b'\0' * (20 * 1024), 1.1)
        self.assertEqual(len(events), 1)
        detector = self.active()
        self.assertFalse(detector.poll(1.3))
        self.assertFalse(detector.feed(b'\1' * 1024, 1.4))
        detector.feed(b'\1' * 100, 1.41)
        stopped = detector.finish('commit', 1.42, partial=True)
        self.assertEqual(len(stopped[0]['pcm']), 4196)
        detector.clear()
        self.assertFalse(detector.poll(100))
        self.assertEqual(detector.feed(b'\1' * 3072, 101)[0]['type'], 'speech_started')

    def test_maximum_utterance(self):
        detector = self.active()
        events = detector.feed(b'\1' * (25 * 32000), 1.1)
        self.assertTrue(any(e.get('reason') == 'max-duration' for e in events))


class TtsTests(unittest.IsolatedAsyncioTestCase):
    async def test_prefetch_tail_pacing_and_finish(self):
        queue = asyncio.Queue()
        for text in ('一', '二', None):
            queue.put_nowait(text)
        audio = {'一': b'a' * 10002, '二': b'b' * 1982}
        sent, events, generated = bytearray(), [], []
        async def synth(text):
            generated.append((text, len(sent)))
            await asyncio.sleep(.001)
            return audio[text]
        async def send(frame):
            sent.extend(frame)
        async def event(name):
            events.append((name, len(sent)))
        start = asyncio.get_running_loop().time()
        await deliver(queue, synth, send, event, lead_seconds=.06)
        self.assertEqual(bytes(sent), audio['一'] + audio['二'])
        self.assertEqual(events[-1], ('task-finished', len(sent)))
        self.assertEqual([n for n, _ in events].count('result-generated'), 2)
        self.assertLess(generated[1][1], len(audio['一']))
        self.assertGreater(asyncio.get_running_loop().time() - start, .2)

    async def test_cancel_stops_pending_audio(self):
        queue = asyncio.Queue()
        queue.put_nowait('一'); queue.put_nowait('二'); queue.put_nowait(None)
        sent, events = [], []
        started = asyncio.Event()
        async def synth(text):
            return b'a' * 64000
        async def send(frame):
            sent.append(frame); started.set()
        async def event(name):
            events.append(name)
        task = asyncio.create_task(deliver(queue, synth, send, event))
        await started.wait()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        count = len(sent)
        await asyncio.sleep(.08)
        self.assertEqual(count, len(sent))
        self.assertNotIn('task-finished', events)

    def test_long_text_tail(self):
        text = '这是长句，' * 30 + '保留最后三个字。'
        parts = list(split_text(text))
        self.assertEqual(''.join(parts), text)
        self.assertLessEqual(max(map(len, parts)), 80)


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from support import configured_server
        cls.context = configured_server()
        cls.context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None, None, None)

    def test_no_stale_asr_after_clear(self):
        import server
        from fastapi.testclient import TestClient
        entered, release = threading.Event(), threading.Event()
        class Asr:
            count = 0
            def transcribe(self, pcm):
                self.count += 1
                if self.count == 1:
                    entered.set()
                    if not release.wait(3):
                        raise TimeoutError('test did not release ASR')
                    return '旧结果'
                return '新结果'
        headers = {'Authorization': 'Bearer ' + server.CONFIG['api_key']}
        append = {'type': 'input_audio_buffer.append', 'audio': base64.b64encode(b'\1' * 3072).decode()}
        with patch.object(server, 'asr', Asr()), patch.object(server, 'SpeechVad', FakeVad):
            with TestClient(server.app).websocket_connect('/api-ws/v1/realtime', headers=headers) as ws:
                ws.send_json({'type': 'session.update'})
                self.assertEqual(ws.receive_json()['type'], 'session.created')
                ws.send_json(append); ws.send_json({'type': 'input_audio_buffer.commit'})
                self.assertEqual(ws.receive_json()['type'], 'input_audio_buffer.speech_started')
                self.assertEqual(ws.receive_json()['type'], 'input_audio_buffer.speech_stopped')
                self.assertTrue(entered.wait(2))
                ws.send_json({'type': 'input_audio_buffer.clear'})
                self.assertEqual(ws.receive_json()['type'], 'input_audio_buffer.cleared')
                release.set()
                ws.send_json(append); ws.send_json({'type': 'input_audio_buffer.commit'})
                self.assertEqual(ws.receive_json()['type'], 'input_audio_buffer.speech_started')
                self.assertEqual(ws.receive_json()['type'], 'input_audio_buffer.speech_stopped')
                self.assertEqual(ws.receive_json()['transcript'], '新结果')

    def test_invalid_tool_and_stream_cancellation_drain(self):
        import server
        class Llm:
            drained = False
            def chunks(self, tokens, limit, stop):
                yield '<think>'
                self.drained = True
        model = Llm()
        stop = threading.Event()
        with patch.object(server, 'llm', model):
            with self.assertRaises(ValueError):
                list(server.generate_events({'tools': []}, [], 30, stop))
        self.assertTrue(model.drained)
        self.assertTrue(stop.is_set())
        for arguments in ({'yaw': 90}, {'yaw': True}, {'yaw': '20'}):
            class BadLlm:
                def chunks(self, *args):
                    yield '<tool_call>' + json.dumps({'name': 'self_arm_yaw', 'arguments': arguments}) + '</tool_call>'
            with patch.object(server, 'llm', BadLlm()), self.assertRaises(ValueError):
                list(server.generate_events({'tools': TOOLS}, [], 100, threading.Event()))

    def test_no_false_action_success_without_tool(self):
        import server
        class Llm:
            def chunks(self, *args):
                yield '害羞表演已启动。'
        with patch.object(server, 'llm', Llm()):
            events = list(server.generate_events({'tools': TOOLS, '_local_route': 'tool-inference'}, [], 80, threading.Event()))
        self.assertIn('还没有执行', events[0]['content'])
        self.assertNotIn('已启动', events[0]['content'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
