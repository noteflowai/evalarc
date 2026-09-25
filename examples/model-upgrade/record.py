"""Record fresh local generations with strict checkpoint loading and original outputs."""

import argparse
import hashlib
import importlib.metadata
import json
import time
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--vision", action="store_true")
    parser.add_argument("--fix-dense-fp8-skip", action="store_true")
    parser.add_argument("--additional-protocol", type=Path)
    parser.add_argument("--additional-output", type=Path)
    args = parser.parse_args()
    if bool(args.additional_protocol) != bool(args.additional_output):
        parser.error("Both additional paths are required")
    jobs = [(args.protocol, args.output)]
    if args.additional_protocol:
        jobs.append((args.additional_protocol, args.additional_output))
    for protocol, destination in jobs:
        if destination.exists():
            raise ValueError(f"Use a new output directory: {destination}")
        json.loads(protocol.read_bytes())
    print("IMPORT_RUNTIME", flush=True)
    import torch
    from transformers import (
        AutoConfig,
        AutoModelForCausalLM,
        AutoModelForImageTextToText,
        AutoProcessor,
        AutoTokenizer,
    )

    torch.set_num_threads(4)
    print("LOAD_PROCESSOR", flush=True)
    processor = (AutoProcessor if args.vision else AutoTokenizer).from_pretrained(
        args.model,
        local_files_only=True,
    )
    config = AutoConfig.from_pretrained(args.model, local_files_only=True)
    adjustments = []
    if args.fix_dense_fp8_skip:
        if config.architectures != ["Qwen3_5ForConditionalGeneration"]:
            raise ValueError(
                "Dense FP8 workaround is specific to the reviewed Qwen3.5 architecture"
            )
        quant = config.quantization_config
        if quant["quant_method"] != "fp8":
            raise ValueError("Expected an FP8 checkpoint")
        names = quant["modules_to_not_convert"]
        removed = [name for name in names if name.endswith(".mlp.gate")]
        quant["modules_to_not_convert"] = [name for name in names if name not in removed]
        adjustments.append(
            {
                "kind": "remove_nonexistent_dense_moe_router_exclusions",
                "removed": removed,
                "reason": (
                    "Transformers 5.17.0 regex-prefix matching otherwise excludes gate"
                    "_proj and discards its FP8 scales. Dense Qwen3.5 has no mlp.gate "
                    "router. Original checkpoint bytes are unchanged."
                ),
            }
        )
    print("LOAD_MODEL", flush=True)
    model, loading = (
        AutoModelForImageTextToText if args.vision else AutoModelForCausalLM
    ).from_pretrained(
        args.model,
        config=config,
        local_files_only=True,
        device_map="cuda:0",
        dtype=torch.bfloat16,
        output_loading_info=True,
    )
    if any(
        loading.get(key)
        for key in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs")
    ):
        raise ValueError("Checkpoint did not load exactly: " + json.dumps(loading, default=str))
    model.eval()
    versions = {}
    for name in (
        "torch",
        "transformers",
        "tokenizers",
        "kernels",
        "flash-linear-attention",
        "triton",
    ):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    identity = {
        "model": args.model_id,
        "revision": args.revision,
        "versions": versions,
        "gpu": torch.cuda.get_device_name(0),
        "dtype": "bfloat16",
        "quantization": getattr(model.config, "quantization_config", None),
        "runtime_adjustments": adjustments,
        "loading_info": {
            key: sorted(value) if isinstance(value, set) else value
            for key, value in loading.items()
        },
        "recorder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    if hasattr(identity["quantization"], "to_dict"):
        identity["quantization"] = identity["quantization"].to_dict()
    print("READY; all checkpoint keys accounted for", flush=True)
    for protocol, destination in jobs:
        raw = protocol.read_bytes()
        spec = json.loads(raw)
        protocol_hash = hashlib.sha256(raw).hexdigest()
        destination.mkdir(parents=True, exist_ok=False)
        (destination / "protocol.json").write_bytes(raw)
        (destination / "identity.json").write_text(
            json.dumps({**identity, "protocol_sha256": protocol_hash}, indent=2) + "\n"
        )
        for case in spec["cases"]:
            for seed in spec["seeds"]:
                user = case.get(
                    "prompt",
                    json.dumps({k: v for k, v in case.items() if k != "id"}, ensure_ascii=False),
                )
                messages = [
                    {"role": "system", "content": spec["policy"]},
                    {"role": "user", "content": user},
                ]
                if case.get("images"):
                    messages[1]["content"] = [
                        {"type": "image", "url": str((protocol.parent / name).resolve())}
                        for name in case["images"]
                    ] + [{"type": "text", "text": user}]
                options = spec["generation"]
                rendered = processor.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                    enable_thinking=options["enable_thinking"],
                )
                if args.vision:
                    inputs = processor.apply_chat_template(
                        messages,
                        tokenize=True,
                        return_dict=True,
                        return_tensors="pt",
                        add_generation_prompt=True,
                        enable_thinking=options["enable_thinking"],
                    )
                else:
                    inputs = processor(rendered, return_tensors="pt")
                inputs = inputs.to("cuda")
                count = inputs["input_ids"].shape[1]
                torch.manual_seed(seed)
                torch.cuda.reset_peak_memory_stats()
                torch.cuda.synchronize()
                started_at = datetime.now(timezone.utc).isoformat()
                started = time.monotonic()
                with torch.inference_mode():
                    output = model.generate(
                        **inputs,
                        max_new_tokens=options["max_new_tokens"],
                        do_sample=options["temperature"] > 0,
                        temperature=options["temperature"],
                        top_p=options["top_p"],
                        top_k=options["top_k"],
                    )
                torch.cuda.synchronize()
                tokens = output[0, count:]
                tokenizer = processor.tokenizer if args.vision else processor
                record = {
                    "case_id": case["id"],
                    "seed": seed,
                    "started_at": started_at,
                    "messages": [
                        {"role": "system", "content": spec["policy"]},
                        {"role": "user", "content": user},
                    ],
                    "images": case.get("images", []),
                    "rendered_prompt": rendered,
                    "raw_output": tokenizer.decode(tokens, skip_special_tokens=False),
                    "text": tokenizer.decode(tokens, skip_special_tokens=True),
                    "prompt_tokens": count,
                    "completion_tokens": len(tokens),
                    "budget_reached": len(tokens) == options["max_new_tokens"],
                    "generation_seconds": time.monotonic() - started,
                    "cuda_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                    "generation": options,
                    "protocol_sha256": protocol_hash,
                }
                (destination / f"{case['id']}-{seed}.json").write_text(
                    json.dumps(record, ensure_ascii=False, indent=2) + "\n"
                )
                print(
                    json.dumps({"case": case["id"], "seed": seed, "tokens": len(tokens)}),
                    flush=True,
                )


if __name__ == "__main__":
    main()
