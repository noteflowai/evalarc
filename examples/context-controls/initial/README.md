# Equal-length skill context pilot

Six Qwen3-8B attempts compare relevant robot-recording guidance with unrelated descriptive text through the same real Skills Anywhere MCP route. The initial prompt, task, catalog description, tool declarations and budgets are fixed. Each condition is assigned model seeds 17, 41 and 97 in the order recorded before inference. All six attempts remain in summary.json.

Both serialized skill-load payloads contain 476 tokens under the pinned model tokenizer, including file and bundle hashes. This matches only the delivered tool-result payload, not the later generated conversation or total token usage. The preparation preserves the exact payloads, source files, tokenizer identities and actual MCP preflight. tokenization-check.json includes the resulting token IDs.

## Observed results and interpretation

All six delivered programs scored zero and failed strict task completion. Each program's eight independent cases timed out before producing a JSON response. The programs use buffered output without flushing each response; their example commands close stdin and therefore do not exercise the persistent request/response interaction in the grader. These results do not distinguish the correctness of the numerical reasoning behind that protocol failure, and do not establish that either kind of context improves or reduces task ability.

After the planned runs, a separate reference check passed all cases under the same Docker image and grader settings. A diagnostic on the unchanged neutral/02-mcp-17 candidate reproduced the timeout; adding Python's -u runtime option produced a response to the same first request. This diagnostic neither replaces the original score nor establishes that other cases or programs would pass. See diagnostics/ for the reference and exact diagnostic record.

These are public-development controls on one task, not hidden tests or six independent tasks. The earlier 27-trial pilot used its own engineering profiles and library snapshots; results must not be pooled into an efficacy estimate. The initial preparation attempt failed to find an exact token-length match before any inference and is retained separately.

## Reproduction inputs

Use the preserved harness/record_context_controls.py with harness/record_skill_impact.py and the matching EvalArc source, the pinned local Qwen3-8B checkpoint, and a built Skills Anywhere bridge. See preparation/match.json, experiment.json and the complete harness/library snapshots for identities, arguments and budgets. The model server command uses the pinned model revision recorded in experiment.json. Actual candidate code executes in non-root, network-disabled Docker containers; the browser review only displays saved evidence.

Code is MIT; the copied Skills Anywhere library retains its own MIT notice. Robot source-data terms are supplied alongside the bundle. No model weights are redistributed.
