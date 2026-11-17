import bootstrap
import asyncio
import base64
import contextlib
import hmac
import json
import logging
import queue
import re
import threading
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
from bootstrap import ROOT
from tool_parser import ToolStreamParser
from llm_proxy import LlmProxy
from asr_proxy import AsrProxy
from tts_engine import synthesize_async, as_wav, close as close_tts
from tts_pipeline import deliver
from settings import load_config, prepare_directories


def SpeechVad():
    from vad_engine import SpeechVad as Detector
    return Detector()

from endpointing import EndpointDetector
from conversation_policy import prepare_request, validate_arguments
from speech_stream import SpeechStream

CONFIG = load_config()
log = logging.getLogger("rig-local")
llm = None
asr = None
llm_lock = threading.Lock()
http_server = None


@asynccontextmanager
async def lifespan(app):
    global llm, asr
    prepare_directories()
    log.warning("Loading Qwen NPU model")
    llm = await asyncio.to_thread(LlmProxy, CONFIG)
    log.warning("Loading local SenseVoice CPU ASR")
    asr = await asyncio.to_thread(AsrProxy)
    await synthesize_async('')  # Initialize the COM apartment before accepting traffic.
    log.warning("Local ASR/LLM/TTS services ready")
    yield
    await asyncio.to_thread(asr.close)
    await asyncio.to_thread(llm.close)
    await asyncio.to_thread(close_tts)


app = FastAPI(title="RIG ARM local voice services", lifespan=lifespan)


def authenticated(value):
    parts = (value or "").split(" ", 1)
    return (len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].isascii()
            and hmac.compare_digest(parts[1], CONFIG["api_key"]))


def require_auth(request):
    if not authenticated(request.headers.get("authorization")):
        raise HTTPException(401, "A valid local service token is required")


@app.get("/health")
def health():
    return {"service": "rig-local-voice", "ready": llm is not None and asr is not None,
            "llm": {"model": CONFIG["llm_model"], "backend_expected": "AMD Ryzen AI NPU", "hardware_verified": False, "context": CONFIG["llm_max_context"]},
            "asr": {"model": "SenseVoice int8", "device": "CPU"},
            "tts": {"voice": "Microsoft Huihui", "device": "CPU", "sample_rate": 16000},
            "pipeline": {"sentence_streaming": True, "silence_ms": CONFIG.get('asr_silence_ms', 800),
                         "tts_prebuffer_ms": CONFIG.get('tts_prebuffer_ms', 240)}}


@app.post("/local/shutdown")
async def shutdown(request: Request):
    require_auth(request)
    if request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "Shutdown is available only on the PC")
    if http_server is None:
        raise HTTPException(503, "Managed server is unavailable")
    http_server.should_exit = True
    return {"stopping": True}


@app.get("/v1/models")
def models(request: Request):
    require_auth(request)
    return {"object": "list", "data": [{"id": CONFIG["llm_model"], "object": "model", "owned_by": "local"}]}


def generate_events(body, tokens, output_limit, stop):
    parser = ToolStreamParser(body.get("tools"))
    speech = SpeechStream()
    start = time.perf_counter()
    raw_pieces = []
    invalid = None
    with llm_lock:
        if stop.is_set():
            return
        for piece in llm.chunks(tokens, output_limit, stop):
            if invalid:
                continue
            if body.get("tools"):
                raw_pieces.append(piece)
            else:
                try:
                    yield from speech.feed(piece)
                except ValueError as error:
                    # Drain the worker after cancellation so its remaining packets
                    # cannot contaminate the next request's process protocol.
                    invalid = error
                    stop.set()
        if invalid:
            raise invalid
        if not stop.is_set():
            if body.get("tools"):
                buffered = parser.feed("".join(raw_pieces), final=True)
                content = "".join(e.get("content", "") for e in buffered)
                spoken = speech.feed(content, final=True)
                calls = [call for event in buffered for call in event.get('tool_calls', [])]
                if len(calls) > 1:
                    raise ValueError('Multiple actions in one response are not supported')
                schemas = {t['function']['name']: t['function'].get('parameters', {}) for t in body['tools']}
                for call in calls:
                    function = call['function']
                    validate_arguments(json.loads(function['arguments']), schemas[function['name']])
                # A tool request is not evidence that an action has succeeded.
                if calls:
                    yield {'tool_calls': calls}
                else:
                    if body.get('_local_route') in ('tool-inference', 'tool-result-inference') and re.search(
                            r'(?:已经|已|正在)(?:为你|为您|帮你|帮您)?(?:启动|开始|完成|执行|开启|关闭|调整|设置|移动|归位|保存|回放)', content):
                        spoken = [{'content': '这次还没有执行操作，请把要做的单步动作再说一遍。'}]
                    yield from spoken
            else:
                yield from speech.feed("", final=True)
    log.warning("LLM completed in %.2fs, input_tokens=%d, tool_calls=%d", time.perf_counter() - start, len(tokens), parser.index)


@app.post("/v1/chat/completions")
async def chat(request: Request):
    require_auth(request)
    raw = await request.body()
    if len(raw) > 1024 * 1024:
        raise HTTPException(413, "Request too large")
    try:
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise ValueError("Request must be a JSON object")
        messages = body.get("messages", [])
        if not isinstance(messages, list) or not all(isinstance(m, dict) for m in messages):
            raise ValueError("messages must be an array of objects")
        # Earlier experimental responses may still be in robot RAM. Remove the
        # malformed exchange and preceding history so it cannot teach the model
        # to repeat reasoning tags or raw function JSON in later replies.
        bad_history = [i for i, m in enumerate(messages[:-1]) if m.get("role") == "assistant"
                       and isinstance(m.get("content"), str) and ("</think>" in m["content"] or
                       ('"name"' in m["content"] and ('"parameters"' in m["content"] or '"arguments"' in m["content"])))]
        if bad_history:
            body["messages"] = [m for m in messages[:max(bad_history)+1] if m.get("role") == "system"] + messages[max(bad_history)+1:]
        body, immediate = prepare_request(body)
        tokens, limit = ([], 0) if immediate is not None else await asyncio.to_thread(llm.encode_request, body)
    except (ValueError, TypeError, KeyError) as error:
        raise HTTPException(400, str(error)) from error
    stop = threading.Event()
    identity = "chatcmpl-" + uuid.uuid4().hex
    created = int(time.time())
    headers = {'X-Local-Route': body['_local_route'], 'X-Local-Input-Tokens': str(len(tokens))}

    def response_events():
        if immediate is not None:
            yield from immediate
        else:
            yield from generate_events(body, tokens, limit, stop)

    def packet(delta=None, finish=None):
        return {"id": identity, "object": "chat.completion.chunk", "created": created,
                "model": CONFIG["llm_model"], "choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish}]}

    if not body.get("stream", False):
        def complete():
            try:
                events = list(response_events())
            except ValueError:
                events = [{'content': '本地模型生成出错了，这次没有执行操作。'}]
            calls = [c for event in events for c in event.get("tool_calls", [])]
            for call in calls:
                call.pop("index", None)
            message = {"role": "assistant", "content": "".join(e.get("content", "") for e in events)}
            if calls:
                message["tool_calls"] = calls
            return {"id": identity, "object": "chat.completion", "created": created, "model": CONFIG["llm_model"],
                    "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if calls else "stop"}]}
        from fastapi.responses import JSONResponse
        return JSONResponse(await asyncio.to_thread(complete), headers=headers)

    events = queue.Queue()

    def worker():
        try:
            for event in response_events():
                events.put(("delta", event))
        except Exception as error:
            log.exception("LLM request failed")
            if isinstance(error, (ValueError, json.JSONDecodeError)):
                events.put(("delta", {"content": "本地模型生成出错了，这次没有执行操作。"}))
            else:
                events.put(("error", str(error)))
        finally:
            events.put(("end", None))

    threading.Thread(target=worker, daemon=True).start()

    async def stream():
        has_tools = False
        try:
            yield "data: " + json.dumps(packet({"role": "assistant"})) + "\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    kind, value = events.get_nowait()
                except queue.Empty:
                    # Byte-level heartbeat also satisfies the ESP32's 10-second stream watchdog.
                    yield ": keepalive\n\n"
                    await asyncio.sleep(0.025)
                    continue
                if kind == "end":
                    yield "data: " + json.dumps(packet(finish="tool_calls" if has_tools else "stop")) + "\n\n"
                    yield "data: [DONE]\n\n"
                    break
                if kind == "error":
                    yield "data: " + json.dumps({"error": {"message": value}}) + "\n\n"
                    break
                has_tools |= "tool_calls" in value
                yield "data: " + json.dumps(packet(value), ensure_ascii=False) + "\n\n"
        finally:
            stop.set()
    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", **headers})


@app.post("/v1/audio/speech")
async def speech(request: Request):
    require_auth(request)
    data = await request.json()
    text = data.get("input", "")
    pcm = await synthesize_async(text)
    if data.get("response_format") == "pcm":
        return Response(pcm, media_type="application/octet-stream")
    return Response(as_wav(pcm), media_type="audio/wav")


@app.post("/local/asr")
async def transcribe(request: Request):
    require_auth(request)
    pcm = await request.body()
    start = time.perf_counter()
    try:
        text = await asyncio.to_thread(asr.transcribe, pcm)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return {"text": text, "seconds": time.perf_counter() - start}


async def ws_auth(ws):
    await ws.accept()
    if not authenticated(ws.headers.get("authorization")):
        await ws.close(code=1008, reason="Invalid local service token")
        return False
    return True


@app.websocket("/api-ws/v1/inference/")
async def tts_ws(ws: WebSocket):
    if not await ws_auth(ws):
        return
    pending = asyncio.Queue(maxsize=32)
    task_id = None
    job = None
    total_chars = 0
    finishing = False

    async def event(name, **extra):
        await ws.send_json({"header": {"event": name, "task_id": task_id, **extra}, "payload": {}})

    async def synth_worker():
        try:
            await deliver(pending, synthesize_async, ws.send_bytes, event,
                          lead_seconds=CONFIG.get('tts_prebuffer_ms', 240) / 1000)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("TTS worker failed")
            with contextlib.suppress(Exception):
                await event("task-failed", error_code="LOCAL_TTS_ERROR", error_message="Local speech synthesis failed")

    try:
        while True:
            message = await ws.receive_json()
            header = message.get("header", {})
            action = header.get("action")
            if action == "run-task":
                if job is not None:
                    raise ValueError("One task per connection")
                task_id = header.get("task_id", uuid.uuid4().hex)
                await event("task-started")
                job = asyncio.create_task(synth_worker())
            elif action == "continue-task" and job is not None and not finishing:
                text = message.get("payload", {}).get("input", {}).get("text", "")
                if not isinstance(text, str):
                    raise ValueError('TTS input must be text')
                total_chars += len(text)
                if total_chars > 8000:
                    raise ValueError("TTS task too long")
                pending.put_nowait(text)
            elif action == "finish-task" and job is not None and not finishing:
                finishing = True
                pending.put_nowait(None)
            else:
                raise ValueError("Unexpected TTS action")
    except WebSocketDisconnect:
        pass
    except Exception as error:
        with contextlib.suppress(Exception):
            await event("task-failed", error_code="INVALID_REQUEST", error_message=str(error))
    finally:
        if job is not None:
            job.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await job


@app.websocket("/api-ws/v1/realtime")
async def asr_ws(ws: WebSocket):
    if not await ws_auth(ws):
        return
    session_id = "asr-" + uuid.uuid4().hex
    pending = asyncio.Queue(maxsize=2)
    send_lock = asyncio.Lock()
    detector = EndpointDetector(SpeechVad(), CONFIG.get('asr_silence_ms', 800))
    configured = False
    epoch = 0

    async def event(kind, expected_epoch=None, **fields):
        async with send_lock:
            if expected_epoch is None or epoch == expected_epoch:
                await ws.send_json({"type": kind, "event_id": uuid.uuid4().hex, **fields})

    async def recognizer():
        while True:
            item_epoch, pcm = await pending.get()
            if item_epoch != epoch:
                continue
            start = time.perf_counter()
            try:
                text = await asyncio.to_thread(asr.transcribe, pcm)
                log.warning("ASR %.2fs audio -> %.2fs inference", len(pcm) / 32000, time.perf_counter() - start)
                await event("conversation.item.input_audio_transcription.completed",
                            expected_epoch=item_epoch, transcript=text, emotion="")
            except Exception as error:
                await event("error", expected_epoch=item_epoch, error={"message": str(error)})

    async def dispatch(events):
        for item in events:
            if item['type'] == 'speech_started':
                await event('input_audio_buffer.speech_started')
            else:
                await event('input_audio_buffer.speech_stopped')
                log.warning('ASR endpoint reason=%s silence_ms=%.0f', item['reason'], item['silence_ms'])
                if item['pcm']:
                    # Bounded work; never block clear/abort behind queued recognition.
                    pending.put_nowait((epoch, item['pcm']))

    worker = asyncio.create_task(recognizer())
    try:
        while True:
            deadline = detector.deadline()
            timeout = 0.1 if deadline is None else max(0.001, min(0.1, deadline - time.monotonic()))
            try:
                message = await asyncio.wait_for(ws.receive_json(), timeout=timeout)
            except asyncio.TimeoutError:
                await dispatch(detector.poll(time.monotonic()))
                continue
            kind = message.get('type')
            if kind == 'session.update':
                session = message.get('session', {})
                if session.get('sample_rate', 16000) != 16000:
                    raise ValueError('Only 16000 Hz PCM is supported')
                requested = int(session.get('turn_detection', {}).get('silence_duration_ms', 800))
                detector.silence_ms = max(320, min(CONFIG.get('asr_silence_ms', 800), requested))
                configured = True
                await event('session.created', session={'id': session_id})
            elif kind == 'input_audio_buffer.append' and configured:
                pcm = base64.b64decode(message.get('audio', ''), validate=True)
                if len(pcm) > 128000 or len(pcm) % 2:
                    raise ValueError('Invalid audio frame')
                await dispatch(detector.feed(pcm, time.monotonic()))
            elif kind == 'input_audio_buffer.commit':
                await dispatch(detector.finish('commit', time.monotonic(), partial=True))
            elif kind == 'input_audio_buffer.clear':
                epoch += 1
                detector.clear()
                while not pending.empty():
                    pending.get_nowait()
                await event('input_audio_buffer.cleared')
    except WebSocketDisconnect:
        pass
    except Exception as error:
        with contextlib.suppress(Exception):
            await event('error', error={'message': str(error)})
    finally:
        epoch += 1
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker


if __name__ == "__main__":
    import uvicorn
    http_server = uvicorn.Server(uvicorn.Config(app, host=CONFIG["host"], port=CONFIG["port"],
        log_level="info", ws_max_size=2*1024*1024, proxy_headers=False))
    http_server.run()
