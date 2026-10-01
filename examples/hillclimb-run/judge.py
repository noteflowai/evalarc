"""Scripted judge command for evalarc judge-run; stands in for a separate judge model.

Reads one item as JSON on stdin and prints {"verdict": ...}. Grader items pass when the
output names the expected queue; pairwise items prefer the output that does.
"""

import json
import sys

request = json.load(sys.stdin)
item = request["item"]
expected = (item.get("expected") or "").strip()
if request["mode"] == "grader":
    verdict = "pass" if f"queue: {expected}" == item["output"].strip() else "fail"
else:
    a = f"queue: {expected}" == item["output_a"].strip()
    b = f"queue: {expected}" == item["output_b"].strip()
    verdict = "tie" if a == b else ("A" if a else "B")
print(json.dumps({"verdict": verdict}))
