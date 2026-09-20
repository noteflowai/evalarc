"""Serve a pinned local Transformers model for isolated evaluation pilots.

This optional recorder is not imported by EvalArc's standard-library core.
The candidate container receives neither these weights nor a network connection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def verify_model_files(directory: Path, proof: Path, model_id: str, revision: str) -> str:
    """Bind a local load to the explicitly reviewed model-file manifest."""
    raw = proof.read_bytes()
    record = json.loads(raw)
    if record.get("model") != model_id or record.get("revision") != revision:
        raise ValueError("model-file manifest identity differs from the requested model")
    expected = record.get("files")
    if not isinstance(expected, dict) or not expected:
        raise ValueError("model-file manifest is empty")
    observed = {path.name for path in directory.iterdir() if not path.is_dir()}
    if observed != set(expected):
        raise ValueError("model directory file inventory differs from the reviewed manifest")
    for name, identity in expected.items():
        if Path(name).name != name or name in (".", ".."):
            raise ValueError("model-file manifest must use direct file names")
        path = directory / name
        with path.open("rb") as handle:
            actual = hashlib.file_digest(handle, "sha256").hexdigest()
        if actual != identity["sha256"] or path.stat().st_size != identity["bytes"]:
            raise ValueError(f"model file differs from the reviewed manifest: {name}")
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--port", type=int, default=47865)
    parser.add_argument("--model-files", type=Path)
    args = parser.parse_args()

    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if not torch.cuda.is_available():
        raise SystemExit("This recorder requires a working CUDA device")
    model_files_hash = (
        verify_model_files(args.model, args.model_files, args.model_id, args.revision)
        if args.model_files
        else None
    )
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        dtype=torch.bfloat16,
        device_map="cuda:0",
        local_files_only=True,
    ).eval()
    if (
        args.model_files
        and verify_model_files(args.model, args.model_files, args.model_id, args.revision)
        != model_files_hash
    ):
        raise ValueError("model-file manifest changed during loading")
    lock = threading.Lock()
    identity = {
        "model": args.model_id,
        "revision": args.revision,
        "device": torch.cuda.get_device_name(0),
        "dtype": "bfloat16",
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "thinking_enabled": False,
        "model_files_manifest_sha256": model_files_hash,
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
            if self.path not in {"/generate", "/measure"}:
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
                if self.path == "/measure":
                    self.respond(
                        200,
                        {
                            **identity,
                            "prompt_tokens": count,
                            "context_limit": 28_000,
                            "max_new_tokens": budget,
                        },
                    )
                    return
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
