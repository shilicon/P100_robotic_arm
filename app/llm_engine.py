import json
import threading
import time
from bootstrap import ROOT
from history_context import fit_history


class QwenLlm:
    def __init__(self, config):
        import onnxruntime_genai as og
        from transformers import AutoTokenizer
        self.og = og
        self.max_context = config["llm_max_context"]
        self.config = config
        path = ROOT / "models" / config["llm_model"]
        self.model = og.Model(str(path))
        self.tokenizer = og.Tokenizer(self.model)
        self.chat_tokenizer = AutoTokenizer.from_pretrained(str(path), local_files_only=True)

    def encode_request(self, body):
        messages = body.get("messages", [])
        if not messages or len(messages) > 84:
            raise ValueError("Too many conversation messages")
        tools = body.get("tools") or None
        # The device's Qwen-compatible request disables thinking; apply that to the actual template.
        output_limit = min(int(body.get("max_tokens") or self.config.get('llm_output_tokens', 160)), 512)
        if output_limit <= 0:
            raise ValueError("max_tokens must be positive")
        def encode(history):
            prompt = self.chat_tokenizer.apply_chat_template(
                history, tools=tools, tokenize=False, add_generation_prompt=True, enable_thinking=False)
            return self.tokenizer.encode(prompt)
        budget = self.max_context - output_limit
        if body.get('_local_route') in ('chat', 'tool-result'):
            # Prefer a short history for voice latency, while still accepting a
            # longer latest turn or custom system instruction within full context.
            try:
                tokens = fit_history(messages, encode, min(budget, self.config.get('llm_chat_input_tokens', 1024)))
            except ValueError:
                tokens = fit_history(messages, encode, budget)
        else:
            tokens = fit_history(messages, encode, budget)
        return tokens, output_limit

    def chunks(self, tokens, output_limit, stop):
        params = self.og.GeneratorParams(self.model)
        params.set_search_options(max_length=len(tokens) + output_limit, do_sample=self.config.get('llm_do_sample', False),
                                  temperature=0.6, top_p=0.95, top_k=20, repetition_penalty=1.05)
        generator = self.og.Generator(self.model, params)
        stream = self.tokenizer.create_stream()
        try:
            generator.append_tokens(tokens)
            while not generator.is_done() and not stop.is_set():
                generator.generate_next_token()
                text = stream.decode(generator.get_next_tokens()[0])
                if text:
                    yield text
        finally:
            del generator



from tool_parser import ToolStreamParser  # Compatibility for offline evaluators.
