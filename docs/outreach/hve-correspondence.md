# Draft note to the hack-verifiable environments authors

**Status: submitted 2026-09-15** as [issue #4](https://github.com/MajoRoth/hack-verifiable-environments/issues/4), on the maintainer's instruction. This is a research
note about a correspondence between two lines of work, not a request for a link or a mention.
Nothing here claims review, agreement or endorsement by the HVE authors.

Target: <https://github.com/MajoRoth/hack-verifiable-environments> (issues enabled). Papers:
[arXiv:2605.20744v1](https://arxiv.org/abs/2605.20744v1) introducing HVE, and
[arXiv:2608.22103v1](https://arxiv.org/abs/2608.22103v1) applying it to Terminal Bench.

---

## Suggested title

A grader-side dual of HVE: planting faults in submissions to measure detector sensitivity

## Suggested body

Maintainer disclosure: I maintain EvalArc, an independent MIT-licensed research preview
developed with AI assistance. This note was prepared by an assistant on the maintainer's
behalf. I am not affiliated with the HVE work and claim no agreement from its authors. I am
raising a correspondence and one measurement that may be useful, and I want to state the
difference precisely rather than imply an equivalence.

### The correspondence, and where it stops

HVE embeds a detectable hacking opportunity in the environment and measures whether the agent
exploits it. EvalArc embeds a declared fault in the submission and measures whether the
evaluation's own checks catch it.

|  | HVE / HVTB | EvalArc audit |
| --- | --- | --- |
| What is planted | A detectable hacking opportunity, in the environment | A declared fault, in the submission |
| Subject measured | The agent | The grader and its checks |
| Question | Does the agent exploit it? | Does the evaluation catch it, and by how much? |
| Reported | Reward-hacking rate across models | Detection of every declared fault, with margins |

EvalArc is not an HVE implementation and does not measure reward hacking. Both lines plant
things so that measurement can be automatic and deterministic rather than resting on trajectory
inspection or an LLM judge, which is the unreliability your 2608.22103 abstract names directly.
They probe opposite directions of the same failure: an evaluation signal that has come apart
from intent.

### Why the grader side may matter to the agent side

HVE takes for granted that a planted hack is detectable by construction, which is what makes an
exploitation rate meaningful. That assumption is exactly what the grader-side measurement puts a
number on, and the number turned out to be less comfortable than a headline suggests.

Across three task packs, every declared fault is detected: 21 of 21, mutation score 1.0. That
reads like a grader with nothing to worry about. Aggregating which cases caught each fault
shows something else: **six of the twenty-one are caught by exactly one case each.** Remove or
loosen that single case and the fault becomes undetected while the score still reads 1.0.

In HVE terms, a fault whose detectability rests on one check is a fault that would become an
*undetected* hack if that check were absent or weakened. So a margin is a measure of how much
of an evaluation's integrity depends on individual checks, and a suite can be at 1.0 while
sitting one edit away from blindness in six places.

One implementation detail that cost us a wrong number first: margins have to count distinct
cases, not case runs. With two seeds the raw failing list for one mutant is six entries over
three cases, so counting runs would double every margin per added seed and a suite would look
twice as robust for changing nothing. A single-seed test cannot tell the two apart, which is
how it got past us.

### If any of it is useful

The margin computation is about forty lines and reads the audit output that already exists; it
is MIT licensed and reusable. The comparable numbers are in
[the methodology](https://github.com/noteflowai/evalarc/blob/main/docs/methodology.md#relation-to-hack-verifiable-environments),
which cites both papers with the conservative venue handling the project's citation record
uses, and states the difference above rather than blurring it.

What I would find genuinely useful in return, if you have a view: whether the detection margin
of a planted hack is something HVE could report alongside the hacking rate. A hack that only
one check would have caught is arguably a weaker instrument than one that several would, and if
so the two measurements are complements in a stronger sense than a table of differences.

Scope, stated plainly: EvalArc runs scripted controls, not models. It ranks nothing, bounds
nothing about reward hacking, and its denominator is a pack's declared fault models rather than
the space of possible exploits. No model results, RL results or benchmark scores are claimed.

---

## Verification behind the claims above

| Claim | How it was checked |
| --- | --- |
| 21 of 21 declared faults detected across three packs | `audit` on `durable-kv`, `support-routing` and `robot-evidence-review`, 8 + 7 + 6, each reporting a mutation score of 1.0 |
| Six rest on a single case each | The `detection.single_case_detections` list across the three packs: three, two and one entry |
| Removing one case would lose the fault at an unchanged score | The sole detectors are named per pack in `detection.sole_detector_cases` |
| Margins count distinct cases, not runs | A two-seed audit reproduces identical margins, and the raw failing list for `ack-without-work` is six entries over three cases |
| Identical under both reference implementations | The same margins under the Python and JavaScript references, for all three packs |

## What this deliberately does not do

- It does not ask for a link, a citation or a mention.
- It does not describe EvalArc as measuring reward hacking, and says the opposite.
- It opens one issue. If a discussion thread or an email suits the authors better, that is where
  this should go instead of being duplicated.
