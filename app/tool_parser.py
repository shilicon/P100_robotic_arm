"""Parse tool calls without loading an inference runtime."""
import json
import time


class ToolStreamParser:
    """Convert Qwen tool-call tags into Chat Completions deltas without leaking tags to TTS."""
    OPEN = "<tool_call>"
    CLOSE = "</tool_call>"

    def __init__(self, tools):
        self.allowed = {t["function"]["name"] for t in tools or []}
        self.buffer = ""
        self.in_tool = False
        self.index = 0

    def feed(self, text, final=False):
        self.buffer += text
        output = []
        while self.buffer:
            if self.in_tool:
                end = self.buffer.find(self.CLOSE)
                if end < 0:
                    if final:
                        raise ValueError("Model returned an incomplete tool call")
                    break
                call = json.loads(self.buffer[:end].strip())
                name = call.get("name", "")
                if name not in self.allowed and name.replace(".", "_") in self.allowed:
                    name = name.replace(".", "_")
                arguments = call.get("arguments", call.get("parameters", {}))
                if name not in self.allowed or not isinstance(arguments, dict):
                    raise ValueError(f"Model returned an invalid tool call: {call!r}")
                output.append({"tool_calls": [{"index": self.index,
                    "id": f"call_local_{time.time_ns()}", "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}]})
                self.index += 1
                self.buffer = self.buffer[end + len(self.CLOSE):]
                self.in_tool = False
            else:
                start = self.buffer.find(self.OPEN)
                if start >= 0:
                    if self.buffer[:start].strip():
                        output.append({"content": self.buffer[:start]})
                    self.buffer = self.buffer[start + len(self.OPEN):]
                    self.in_tool = True
                else:
                    keep = 0 if final else len(self.OPEN) - 1
                    emit = self.buffer if keep == 0 else self.buffer[:-keep]
                    if emit:
                        output.append({"content": emit})
                        self.buffer = self.buffer[len(emit):]
                    break
        return output
