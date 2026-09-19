"""Implement the recording-review contract described in TASK.md."""

import json
import sys


def review(request):
    raise NotImplementedError("Convert recorded observations and return the requested facts")


for line in sys.stdin:
    print(json.dumps({"ok": True, "report": review(json.loads(line))}), flush=True)
