"""Scripted evaluation for the hillclimb-run example; no model is called.

A stand-in agent routes a ticket correctly when rules.md has a topic rule
("route <topic> -> <queue>") or a case rule ("case <id> -> <queue>") for it.
Writes an Inspect-format log with two epochs per ticket to the path in argv[1].
"""

import json
import re
import sys
from pathlib import Path

rules = Path("rules.md").read_text()
topics = dict(re.findall(r"^route (\w+) -> (\w+)$", rules, re.M))
cases = dict(re.findall(r"^case (\w+) -> (\w+)$", rules, re.M))
pasted = {
    line.split(" -> ")[0]: line.split(" -> ")[1]
    for line in rules.splitlines()
    if line.startswith("Ticket ") and " -> " in line
}
samples = []
for ticket in json.loads(Path("tickets.json").read_text()):
    route = (
        cases.get(ticket["id"])
        or pasted.get(ticket["text"])
        or topics.get(ticket["topic"], "general")
    )
    for epoch in (1, 2):
        samples.append(
            {
                "id": ticket["id"],
                "epoch": epoch,
                "input": ticket["text"],
                "target": ticket["queue"],
                "output": {
                    "model": "scripted/router",
                    "choices": [],
                    "completion": f"queue: {route}",
                },
                "scores": {
                    "route": {"value": "C" if route == ticket["queue"] else "I", "answer": route}
                },
                "model_usage": {"scripted/router": {"total_tokens": 300 + len(rules) // 4}},
            }
        )
log = {
    "status": "success",
    "eval": {
        "task": "ticket_routing",
        "model": "scripted/router",
        "config": {"epochs": 2},
        "scorers": [{"name": "route"}],
    },
    "samples": samples,
}
Path(sys.argv[1]).write_text(json.dumps(log, indent=1) + "\n")
