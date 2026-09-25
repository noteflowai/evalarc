# Your first EvalArc review

Start with a recorded failure, check it on your machine, then use the same
workflow with your own evidence. The steps below use the published **0.14.0**
reviewer with the original **0.12.1** evidence snapshot. The two versions are
pinned separately so the tool can advance while the recorded inputs stay fixed.
You need Python 3.11+ on Linux and `curl` for downloads.
The review does not need a source checkout, Docker, Node, a GPU or a model key.

## 1. See the problem

[Open the revision comparison](https://noteflowai.github.io/evalarc/#regression).
The score rises from **90% to 93.75%**, but the notes check regresses. Two
closure checks improve. Select `retry-after-commit` to see the duplicate note.

These are saved Docker runs of scripted controls. They illustrate a grader
and a workflow, not a customer's incident or a model ranking.

## 2. Install the reviewer

Use a new folder so that existing downloads and outputs stay separate:

```bash
mkdir evalarc-first-review
cd evalarc-first-review
python3 -m venv .venv
. .venv/bin/activate
python -m pip install evalarc==0.14.0
evalarc --version
```

Expected: `EvalArc 0.14.0`. This installs the released wheel from PyPI, with no
third-party runtime dependencies. The same wheel is available from GitHub
Releases with a [checksum-pinned installation command](publication.md#python-distributions).

## 3. Recompute the recorded regression

```bash
curl --fail --location \
  https://github.com/noteflowai/evalarc/releases/download/v0.12.1/evalarc-evidence-explorer.zip \
  --output evalarc-evidence-explorer.zip
python -m zipfile -e evalarc-evidence-explorer.zip .
evalarc verify evalarc-evidence-explorer/comparison --json
evalarc compare evalarc-evidence-explorer/comparison/baseline.json \
  evalarc-evidence-explorer/comparison/current.json \
  --output comparison-review
```

The verification exits **0**: the records are consistent. The comparison exits
**1**: one check regressed, even though the score improved. Open
`comparison-review/index.html` directly in your browser to inspect the result.
It works offline. Use a new output folder when repeating the comparison.

The released ZIP has SHA-256
`4ac78211c718dc930a0091227e0d4d9baf0543e05222792d82e05cb44362a073`;
all release checksums are in `SHA256SUMS` on the
[release page](https://github.com/noteflowai/evalarc/releases/tag/v0.12.1).

## 4. Check the acceptance decision

```bash
evalarc verify evalarc-evidence-explorer/suite --json
evalarc verify evalarc-evidence-explorer/suite --json --require-accepted
```

The first command exits **0** for consistency; the second exits **1** because
the strict notes gate rejects the policy. Across the recorded suite, **2/3
jobs are accepted and 1/3 is fully resolved**. A configured gate accepting
partial progress does not mean every task check passed.

Open `evalarc-evidence-explorer/suite/index.html` to inspect the rules. Keep
`suite/junit.xml` with the original suite if you hand the report to someone
else. [Verification checks and limits](verification.md) explain what is
recomputed; this is not a fresh execution of the candidate or authentication
of the producer.

## 5. Use your own evidence

| What you have | Next step |
| --- | --- |
| Two EvalArc evaluations of a candidate | Replace the two JSON inputs to `evalarc compare`; keep matching tasks, graders, cases and runtime conditions. [Workflow](workflow.md) |
| Strands Evals cases and observed state | Follow the optional native SDK example, with explicit state rules and per-row verdict comparison. [State-review recipe](../examples/strands-state-review/README.md) |
| Saved AgentCore Evaluate results and spans | Prepare the bounded input wrapper, import locally, and inspect missing judgments as well as rejected gates. [Export-to-review walkthrough](agentcore-first-review.md) |
| A coding or tool-using candidate to execute | Run a task audit or evaluate its workspace with the Docker backend. [Run an audit](../README.md#run-an-audit) |
| Repeated judgments on one fixed trace | Check score variation and verdict disagreement separately. [Judge Stability](judge-stability.md) |
| Correct final files with questionable runtime actions | Recheck temporary writes and service requests from the released evidence bundle. [Local behavior review](behavior-first-review.md) |

## Share a useful first-use report

If you try your own records, a small
[first-use report](https://github.com/noteflowai/evalarc/issues/new?template=first-use.yml)
helps improve the workflow: what you were reviewing, where you got stuck, and
whether the result changed a decision. A failed setup is useful feedback too.
Only include a minimal redacted example; private prompts, customer data and
credentials are not needed.

The first-use form is an invitation for independent feedback. It is not a
claim that independent users have completed this workflow.
