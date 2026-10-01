"""Propose one change to prompt.md for `evalarc hillclimb-run`. Replace with your model call.

    python propose.py FAILURES.json

FAILURES.json lists failing tuning cases only, each with a likely cause. A good
proposal fixes the root cause of the most common consistent_failure (a missing or
wrong rule) in one focused edit. Do not paste case inputs or expected answers into
prompt.md: such patches are rolled back before evaluation. Skip pipeline, truncated
and grader_inconsistent cases; editing the prompt does not fix them.

This stub makes no change, so every iteration is recorded as no_change.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

failures = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["failures"]
consistent = [item for item in failures if item["category"] == "consistent_failure"]
print(
    f"{len(failures)} failing tuning case(s), {len(consistent)} consistent failure(s). "
    "Replace propose.py with a model call that edits prompt.md."
)
