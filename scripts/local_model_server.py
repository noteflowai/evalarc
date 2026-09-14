"""Serve a pinned local Transformers model for isolated evaluation pilots.

This optional recorder is not imported by EvalArc's standard-library core.
The candidate container receives neither these weights nor a network connection.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--port", type=int, default=47865)
    args = parser.parse_args()

    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if not torch.cuda.is_available():
        raise SystemExit("This recorder requires a working CUDA device")
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        dtype=torch.bfloat16,
        device_map="cuda:0",
        local_files_only=True,
    ).eval()
    lock = threading.Lock()
    identity = {
        "model": args.model_id,
        "revision": args.revision,
        "device": torch.cuda.get_device_name(0),
        "dtype": "bfloat16",
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "thinking_enabled": False,
    }

    class Handler(BaseHTTPRequestHandler):
        def respond(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *values: object) -> None:
            # Do not put prompts or responses in the service's diagnostic log.
            print(format % values, flush=True)

        def do_GET(self) -> None:
            self.respond(200 if self.path == "/health" else 404, identity)

        def do_POST(self) -> None:
            if self.path != "/generate":
                self.respond(404, {"error": "unknown endpoint"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 1 <= size <= 2_000_000:
                    raise ValueError("request must be between 1 and 2000000 bytes")
                data = json.loads(self.rfile.read(size))
                messages = data["messages"]
                tools = data.get("tools")
                budget = data.get("max_new_tokens", 2048)
                seed = data.get("seed", 17)
                temperature = data.get("temperature", 0.2)
                if not isinstance(messages, list) or not 1 <= len(messages) <= 100:
                    raise ValueError("provide between 1 and 100 messages")
                if type(budget) is not int or not 1 <= budget <= 4096:
                    raise ValueError("generation budget must be between 1 and 4096")
                if type(seed) is not int or not 0 <= seed < 2**32:
                    raise ValueError("seed must be an unsigned 32-bit integer")
                if type(temperature) not in (float, int) or not 0 <= temperature <= 2:
                    raise ValueError("temperature must be between 0 and 2")
                prompt = tokenizer.apply_chat_template(
                    messages,
                    tools=tools,
                    tokenize=False,
                    add_generation_prompt=True,
                    enable_thinking=False,
                )
                inputs = tokenizer(prompt, return_tensors="pt")
                count = inputs["input_ids"].shape[1]
                if count + budget > 28_000:
                    raise ValueError("prompt and generation exceed the pilot context budget")
                with lock, torch.inference_mode():
                    inputs = inputs.to("cuda")
                    torch.manual_seed(seed)
                    torch.cuda.reset_peak_memory_stats()
                    torch.cuda.synchronize()
                    started = time.monotonic()
                    options = {
                        "max_new_tokens": budget,
                        "do_sample": temperature > 0,
                        "pad_token_id": tokenizer.eos_token_id,
                    }
                    if temperature > 0:
                        options.update(temperature=temperature, top_p=0.9, top_k=20)
                    output = model.generate(**inputs, **options)
                    torch.cuda.synchronize()
                    duration = time.monotonic() - started
                    generated = output[0, count:]
                    text = tokenizer.decode(generated, skip_special_tokens=False)
                    text = text.removesuffix("<|im_end|>")
                    result = {
                        **identity,
                        "text": text,
                        "prompt_tokens": count,
                        "completion_tokens": generated.shape[0],
                        "wall_seconds": duration,
                        "cuda_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                        "seed": seed,
                        "temperature": temperature,
                        "max_new_tokens": budget,
                        "generation_budget_reached": generated.shape[0] == budget,
                    }
                self.respond(200, result)
            except (ValueError, KeyError, TypeError, RuntimeError) as error:
                self.respond(400, {"error": f"{type(error).__name__}: {error}"})

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(json.dumps({"ready": True, "port": args.port, **identity}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
