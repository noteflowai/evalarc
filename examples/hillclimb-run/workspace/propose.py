"""Scripted proposer for the hillclimb-run example; stands in for a model.

argv: iteration, path to tuning-failures.json. It reads the failures (to show the
interface), then appends the scripted proposal for this iteration to rules.md.
"""

import json
import sys
from pathlib import Path

iteration, failures = int(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text())
assert failures["held_out_excluded"] and all(
    not f["case_id"].startswith("h") for f in failures["failures"]
)
proposal = json.loads(Path("proposals.json").read_text())[iteration - 1]
if proposal["append"]:
    with open("rules.md", "a") as rules:
        rules.write(proposal["append"] + "\n")
print(json.dumps({"iteration": iteration, "why": proposal["why"]}))
