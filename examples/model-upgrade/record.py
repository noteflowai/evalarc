"""Record fresh local generations, preserving prompts, raw output and model identity."""
import argparse
import hashlib
import json
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--model-id', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--vision', action='store_true')
    args = parser.parse_args()
    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoModelForImageTextToText, AutoProcessor, AutoTokenizer
    torch.set_num_threads(4)
    args.output.mkdir(parents=True, exist_ok=False)
    raw = args.protocol.read_bytes()
    spec = json.loads(raw)
    (args.output / 'protocol.json').write_bytes(raw)
    processor = (AutoProcessor if args.vision else AutoTokenizer).from_pretrained(args.model, local_files_only=True)
    model = (AutoModelForImageTextToText if args.vision else AutoModelForCausalLM).from_pretrained(args.model, local_files_only=True, device_map='cuda:0', dtype=torch.bfloat16).eval()
    identity = {'model': args.model_id, 'revision': args.revision, 'torch': torch.__version__, 'transformers': transformers.__version__, 'gpu': torch.cuda.get_device_name(0), 'dtype': 'bfloat16', 'quantization': getattr(model.config, 'quantization_config', None), 'protocol_sha256': hashlib.sha256(raw).hexdigest()}
    if hasattr(identity['quantization'], 'to_dict'): identity['quantization'] = identity['quantization'].to_dict()
    (args.output / 'identity.json').write_text(json.dumps(identity, indent=2)+'\n')
    print('READY', flush=True)
    for case in spec['cases']:
        for seed in spec['seeds']:
            user = case.get('prompt', json.dumps({k:v for k,v in case.items() if k != 'id'}, ensure_ascii=False))
            messages = [{'role': 'system', 'content': spec['policy']}, {'role': 'user', 'content': user}]
            if case.get('images'):
                messages[1]['content'] = [{'type':'image','url': str((args.protocol.parent / name).resolve())} for name in case['images']] + [{'type':'text','text':user}]
            options = spec['generation']
            rendered = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=options['enable_thinking'])
            if args.vision:
                inputs = processor.apply_chat_template(messages, tokenize=True, return_dict=True, return_tensors='pt', add_generation_prompt=True, enable_thinking=options['enable_thinking'])
            else:
                inputs = processor(rendered, return_tensors='pt')
            inputs = inputs.to('cuda')
            count = inputs['input_ids'].shape[1]
            torch.manual_seed(seed)
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
            started = time.monotonic()
            with torch.inference_mode():
                output = model.generate(**inputs, max_new_tokens=options['max_new_tokens'], do_sample=options['temperature'] > 0, temperature=options['temperature'], top_p=options['top_p'], top_k=options['top_k'])
            torch.cuda.synchronize()
            tokens = output[0, count:]
            text = processor.decode(tokens, skip_special_tokens=False) if not args.vision else processor.tokenizer.decode(tokens, skip_special_tokens=False)
            clean = processor.decode(tokens, skip_special_tokens=True) if not args.vision else processor.tokenizer.decode(tokens, skip_special_tokens=True)
            record = {'case_id': case['id'], 'seed': seed, 'messages': [{'role':'system','content':spec['policy']},{'role':'user','content':user}], 'images':case.get('images',[]), 'rendered_prompt': rendered, 'raw_output': text, 'text': clean, 'prompt_tokens': count, 'completion_tokens': len(tokens), 'budget_reached': len(tokens)==options['max_new_tokens'], 'generation_seconds': time.monotonic()-started, 'cuda_peak_allocated_bytes': torch.cuda.max_memory_allocated(), 'generation': options, 'protocol_sha256': identity['protocol_sha256']}
            (args.output / f"{case['id']}-{seed}.json").write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps({'case':case['id'],'seed':seed,'tokens':len(tokens)}),flush=True)

if __name__ == '__main__':
    main()
