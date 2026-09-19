"""Implement the durable-kv contract from TASK.md."""

import json
import sys

for line in sys.stdin:
    json.loads(line)
    print(json.dumps({"ok": False, "error": "not_implemented"}), flush=True)
