# Run a hillclimbing loop with your own commands

`evalarc hillclimb-run` drives the loop that
[`hillclimb-review`](hillclimb-review.md) audits after the fact. You supply two
commands: one that evaluates the workspace and writes an Inspect AI, promptfoo or
JUnit result, and one that proposes a change (typically by calling a model with
your own key). EvalArc never calls a model. It decides what each command may see
and change, and whether to keep each change. [中文](hillclimb-run.zh-CN.md).

```bash
cp -r examples/hillclimb-run /tmp/climb-example   # the loop edits the workspace
evalarc hillclimb-run /tmp/climb-example/hillclimb.toml --output runs/climb --trust-local
```

```text
  1. keep (tuning +25.0 pp, held out +33.3 pp)
  2. rollback_pasted_case
  3. rollback_overfit (tuning +12.5 pp, held out +0.0 pp) — stalled
  4. no_change
  5. keep (tuning +25.0 pp, held out +50.0 pp)
Stopped: max_iterations | Kept: 05.json | Recommendation: merge
```

The [example](../examples/hillclimb-run/README.md) is scripted: `propose.py`
replays five declared edits instead of calling a model.

## Configuration

```toml
workspace = "workspace"            # relative to this file
allow = ["rules.md"]               # globs the propose command may edit
held_out = "split.json"            # evalarc.case-split.v1
evaluate = ["{python}", "evaluate.py", "{output}"]
propose = ["{python}", "propose.py", "{iteration}", "{failures}"]
objective = "quality"              # or "cost"
max_iterations = 5
stall_after = 2
timeout_seconds = 60
```

Commands are argument arrays run without a shell, in the workspace, with your
environment. Placeholders: `{python}`, `{workspace}`; `{output}` (evaluate: the
result path to write); `{failures}`, `{allowed}`, `{iteration}` (propose). Other
keys: `cost_metric`, `max_cost_ratio`, `min_effect`, `result_suffix` (`.json`,
`.xml`, `.eval`), `format`, `threshold`, `leak_min_chars` (12),
`paste_check` (true).

## Each iteration

1. EvalArc writes `steps/NN/tuning-failures.json`: failing **tuning** cases of
   the last kept result, with inputs, expected answers, outputs, grader evidence
   and a triage category. Held-out cases are never included.
2. The propose command runs. If it changes any workspace file outside `allow`
   (including `.git`; only `__pycache__` and tool caches are ignored), the loop
   restores the allowed files, deletes files it created, and stops with exit 2,
   naming any pre-existing files it modified so you can restore them. If it
   fails, the step is `propose_failed`. Allowed paths turned into symlinks are
   replaced with their kept content.
3. The patch to allowed files is saved as `patch.diff`. Before any evaluation it
   is rolled back as `rollback_leakage` if its added lines contain held-out case
   text, or `rollback_pasted_case` if they contain tuning case text (pasting
   failing cases instead of fixing the cause). Only recorded strings of at least
   `leak_min_chars` characters are checked, so a short answer such as `billing`
   is not caught. An empty patch is `no_change`.
4. Otherwise evaluate runs, and the result is compared with the last kept result
   using the hillclimb-review rules: `keep`, `rollback_regression`,
   `rollback_overfit` or `rollback_no_gain`. Rolled-back files are restored.
5. After `stall_after` consecutive non-keeps, remaining tuning failures are
   triaged; if the tuning headroom is below the resolvable change, the loop stops
   (`stopped_below_noise`).

At the end the workspace holds the last kept version, `original/` holds the
starting files, and `final.diff` the net change. `hillclimb.json`, `summary.md`
and `index.html` are the hillclimb-review report over every evaluated result.
Exit 0 means merge recommended, 1 not recommended, 2 a configuration, command or
safety failure. `loop.json` records every step, including on failure.

## Safety

Both commands run on the host with your privileges and environment, so
`--trust-local` is required. The `allow` guard compares the workspace before
and after each propose command; it does not sandbox the commands, so it cannot
see changes outside the workspace or undo edits to files that already existed.
Run the loop on a copy or a clean git checkout, keep held-out data out of the
workspace, and review `final.diff` before merging.
