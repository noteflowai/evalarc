# Research note: sensitivity checks for deterministic hack labels

Reviewed text prepared for the HVE authors. This document alone is not a
submission receipt or evidence of author agreement.

Target: [Hack-Verifiable Environments](https://github.com/MajoRoth/hack-verifiable-environments).
Background: [HVE, arXiv:2605.20744v1](https://arxiv.org/abs/2605.20744v1) and
[HVTB, arXiv:2608.22103v1](https://arxiv.org/abs/2608.22103v1).
The repository has issues enabled and no Discussions at the time of review.
Check for an existing submission before sending; do not post the same note in
several channels.

## Suggested title

Question: how do you regression-test the deterministic reward_hack labels?

## Suggested body

Maintainer disclosure: I maintain EvalArc, an independent MIT-licensed research
preview developed with AI assistance. This question was prepared by an
assistant on my behalf. I am not affiliated with the HVE authors.

Your README demonstrates `step_info["reward_hack"]` as the signal for whether
a planted opportunity was exploited. Is there a recommended way to test the
detector itself against positive and negative scripted trajectories, including
changes to an instrumentation hook?

The motivation comes from a different setup. EvalArc's audit plants declared
faults in scripted submissions and checks whether the grader detects them.
It does not plant hacking opportunities in an environment, and is not an HVE
implementation or a measurement of model reward hacking.

Our three development task packs detect all 21 declared faults (8 + 7 + 6),
but six are each detected by exactly one distinct case. This led us to report
detecting case IDs beside the mutation score. The margin counts distinct
cases, not repeated seed executions, and makes no statistical-independence
claim.

We also corrected an erroneous explanation of this result: removing the sole
detector does **not** preserve a freshly computed mutation score of 1.0. In a
real reduced-suite run at seed 17, removing `cas-type-sensitivity` leaves the
`boolean-equals-one` fault undetected, changing the durable-kv result from 8/8
to 7/8 (0.875), with weakest margin zero. An old report could remain stale;
a fresh audit exposes the regression.

Would an analogous regression check be useful for HVE's instrumentation—for
example, controlled trajectories that must and must not set each hack flag,
then checking whether disabling a detection hook changes the expected labels?
The units would be hooks and labeled trajectories, rather than directly
transplanting our grader-case margin.

This is a methodological question, not evidence that HVE has a detector bug:
we have not evaluated your instrumentation or run HVE model experiments.
The small reproduction and its limits are in
[our methodology](https://github.com/noteflowai/evalarc/blob/main/docs/methodology.md#detection-margins)
and [the reduced-suite test](https://github.com/noteflowai/evalarc/blob/main/tests/test_grading.py).
If there is already a preferred test or discussion location, a pointer would
be useful; there is no request for a listing, citation or endorsement.

## Verification

| Claim | Evidence |
| --- | --- |
| Three packs detect 21 declared faults | Saved audits: 8 + 7 + 6; original JSON retained |
| Six faults have one detecting case each | Three, two and one in `detection.single_case_detections` |
| A reduced suite lowers the recomputed score | `test_removing_sole_detector_lowers_the_recomputed_mutation_score` runs real scripted controls |
| Repeated seeds must not inflate margins | Existing two-seed regression counts distinct failing case IDs |
| This is not a reward-hacking measurement | No HVE trajectories, model calls or detector-performance claims in this reproduction |
