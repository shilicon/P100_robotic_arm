"""Overlap sentence synthesis and bounded, real-time PCM delivery."""
import asyncio
import re


def split_text(text, target=48, maximum=80):
    text = re.sub(r'[\U0001f000-\U0001ffff\ufe0f]', '', text).strip()
    while len(text) > target:
        matches = list(re.finditer(r'[，,。！？；;：:\n]|\s', text[:maximum]))
        preferred = [m.end() for m in matches if m.end() <= target]
        end = preferred[-1] if preferred else (matches[0].end() if matches else maximum)
        yield text[:end]
        text = text[end:]
    if text:
        yield text


async def deliver(pending, synthesize, send_bytes, event, lead_seconds=0.24):
    audio = asyncio.Queue(maxsize=2)

    async def produce():
        try:
            while True:
                text = await pending.get()
                if text is None:
                    await audio.put(None)
                    return
                for part in split_text(text):
                    await audio.put(('pcm', await synthesize(part)))
                await audio.put(('sentence', None))
        except asyncio.CancelledError:
            raise
        except Exception as error:
            await audio.put(('error', error))

    producer = asyncio.create_task(produce())
    clock = asyncio.get_running_loop().time
    playback_end = clock()
    try:
        while True:
            item = await audio.get()
            if item is None:
                await event('task-finished')
                return
            kind, value = item
            if kind == 'error':
                raise value
            if kind == 'sentence':
                await event('result-generated')
                continue
            for offset in range(0, len(value), 1920):
                frame = value[offset:offset + 1920]
                await asyncio.sleep(max(0, playback_end - clock() - lead_seconds))
                await send_bytes(frame)
                playback_end = max(clock(), playback_end) + len(frame) / 32000
    finally:
        producer.cancel()
        await asyncio.gather(producer, return_exceptions=True)
