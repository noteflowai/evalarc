"""Replace this policy with an agent that executes the task's tool operations."""

import json
import sys

for line in sys.stdin:
    observation = json.loads(line)
    print(json.dumps({"finish": True, "message": "Not implemented."}), flush=True)
