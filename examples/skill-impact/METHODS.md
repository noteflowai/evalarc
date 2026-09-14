# Tool delivery and independently measured task outcomes

All 27 trials use Qwen/Qwen3-8B revision
`b968826d9c46dd6066d109eabc6255188de91218` on an NVIDIA L40S, bfloat16,
with thinking disabled. Each profile schedules seeds 17, 41, 97 for no skill,
direct loading and real MCP stdio delivery. Route order rotates across seeds.
Budgets: 12 model turns, 4,096 generated tokens per turn, 600 seconds before
independent grading, sampling temperature 0.2. Grading uses seeds 41 and 97;
the public development example uses seed 17.

The task interprets real, attributed Robot Reel CUDA recordings in several
coordinate/clock conventions, including missing observations. Derived variants
are not new physical simulations. Numerical answers are checked against the
original world-coordinate records. The reference implementation and six fault
controls pass Python and JavaScript Docker audits.

Candidate code runs in non-networked, non-root Docker containers with no host
mounts or credentials. A receipt identifies returned SKILL.md and bundle bytes;
it does not prove the model followed the advice. Direct and MCP receive identical
model-facing fields, prompts, tool definitions and skill pins within a profile.
“Direct” is this file adapter, not a native named coding agent's skill loader.

The three profiles are engineering iterations:

1. The authoritative contract is in a file. Models sometimes inspect guidance
   before reading the task and produce the wrong output contract.
2. The contract is in the initial context. Some models consume the turn budget
   on lexical searches that miss the original skill description.
3. A clearer description and bounded catalog fallback resolve that discovery
   failure. All direct/MCP trials load the skill, but none passes the task.

No skill-effect gain is claimed. Extra context, search/tool choices and model
behavior are confounded in this small public task. The profiles must not be pooled
as one benchmark; each uses only three seeds per condition.

The first profile's candidates were regraded after separating Docker readiness
from candidate response timing: all nine scores stayed unchanged. Original and
regrade reports remain in the complete experiment archive. An earlier interrupted
development run exposed a workspace-path mismatch; it is documented separately
and is not counted among these three completed profiles.

Every trial retains the candidate, evaluation and ATIF trajectory. ATIF-v1.8
exports were checked with the real Harbor 0.23.0 `Trajectory` schema validator.
EvalArc's lightweight importer checks a narrower bounded envelope and tool-call
linkage; it must not be mistaken for full upstream schema validation.

Workflow completion and task acceptance are separate. A valid evaluation means
the evaluation produced a usable result; it does not mean the candidate passed.
Fractional task scores describe only this task's checks. Wall times are recording
metadata, not a throughput comparison, and hardware cost is not estimated.

The repository scripts preserve the executed harness bytes for the final profile.
The public traces contain only generated development-session data, never the
operator's personal agent history. Recorder and bridge code retain their project
licenses; Robot Reel recording data retains Apache-2.0 attribution included here.
