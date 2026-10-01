"""Run every case through app.respond, grade it, and write an Inspect-format log.

    python evaluate.py OUTPUT.json [--epochs 3]

The log works with every EvalArc command (diff, eval-health, judge-packet,
hillclimb-review, hillclimb-run). Run each case several times (--epochs) so
variance is visible. Each attempt starts from a fresh call: do not keep state,
files or history between attempts, or earlier attempts can leak answers.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from app import load_prompt, respond
from grader import grade

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--epochs", type=int, default=3)
    args = parser.parse_args()
    cases = [
        json.loads(line)
        for line in (HERE / "cases.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    prompt = load_prompt()
    samples = []
    for epoch in range(1, args.epochs + 1):
        for case in cases:
            sample = {
                "id": case["id"],
                "epoch": epoch,
                "input": case["input"],
                "target": case["expected"]
                if isinstance(case["expected"], str)
                else json.dumps(case["expected"]),
            }
            started = time.perf_counter()
            try:
                output = respond(case["input"], prompt)
            except Exception as error:  # an app failure is a pipeline error, not a grade
                sample["error"] = {"message": f"{type(error).__name__}: {error}"}
                samples.append(sample)
                continue
            passed, explanation = grade(case, output)
            sample |= {
                "output": {"model": "app", "choices": [], "completion": output},
                "scores": {
                    case["check"]: {
                        "value": "C" if passed else "I",
                        "answer": output,
                        "explanation": explanation,
                    }
                },
                "working_time": time.perf_counter() - started,
            }
            samples.append(sample)
    log = {
        "version": 2,
        "status": "success",
        "eval": {
            "task": "my_eval",
            "model": "app",
            "config": {"epochs": args.epochs},
            "scorers": [{"name": name} for name in sorted({c["check"] for c in cases})],
        },
        "samples": samples,
    }
    args.output.write_text(json.dumps(log, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
