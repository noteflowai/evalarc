# EvalArc roadmap

Updated: 2026-09-29 · Owner: NoteFlowAI maintainer · Review: weekly; reassess priorities monthly.

This proposed roadmap supersedes the priorities in the earlier [version roadmap](docs/roadmap.md). Now / Next / Later is a sequence of evidence gates, not a release-date promise.

## User and outcome

For an engineer changing an agent or model, answer **which important behaviors regressed, what evidence supports that decision, and should this change pass CI?**

Keep the recorded-input → comparable checks → understandable report → explicit gate workflow small, offline-capable and provider-neutral.

## Current baseline

Reviewed `91e3d63` / v0.16.0. Import, per-check comparison, report/gate workflows, judge stability and model/recorded-decision examples already exist. The earlier roadmap ending around v0.12 is no longer an accurate inventory of missing functionality.

External CI adoption, decision time and false-alarm rates are unmeasured here. Synthetic fixtures and live-model examples must remain separately labeled.

## Now

| ID | Outcome | Acceptance evidence |
| --- | --- | --- |
| EA-01 | An engineer gates an existing evaluation without rewriting it | Test one Inspect AI and one promptfoo/JUnit path against permitted real exports. Document field loss, identity matching and unsupported cases. A clean checkout produces the expected report and CI exit code; observe three first-use attempts. |
| EA-02 | Missing evidence cannot look like an improvement | Build a stable regression corpus containing added/removed checks, unequal coverage, malformed records, duplicate IDs and non-comparable runs. The gate explains inconclusive cases rather than silently passing them. Reuse existing coverage logic. |
| EA-03 | Reviewers understand why a gate fired | Show the smallest reproducible example, source provenance, threshold and uncertainty for each blocking finding. Measure time to locate the cause; trial target is under ten minutes on a known regression. |

## Next

| ID | Outcome | Entry and exit gates |
| --- | --- | --- |
| EA-04 | Judge calibration has measured value | Begin only with a labeled, permitted corpus. Separate train/calibration and held-out evaluation; report disagreement, false positives, false negatives and missing judgments. Do not claim broad benchmark superiority from scripted examples. |
| EA-05 | Evidence transfers across specialized tools | Version a small import/export contract with Robot Reel and the automation controller. Accept recorded evidence without taking over robot replay, execution or publication. Demonstrate backwards-compatible fixtures. |

## Later

Add provider adapters only in response to a concrete user dataset and a maintainer willing to test compatibility. Hosted dashboards, model training and a general orchestration engine are outside the current product.

## Measures and review

- Establish a baseline from three independent evaluation workflows; record setup time and blockers.
- Track repeated gate use, reviewer decision time and false alarms on labeled cases.
- Count a report as useful when it changes or confirms a real engineering decision with evidence. Report volume alone is not success.
- If users repeatedly ignore a gate, examine calibration and explanation before adding import formats.
- Publish limitations and evidence changes with releases; retain input hashes and gate configuration.

## Task and release policy

One active milestone. Every proposed change links its milestone ID, user problem, reproduction and acceptance check. Maintenance, documentation that resolves an observed blocker, and a justified no-change outcome are valid. Existing CLI compatibility, regression tests and exact-version package checks remain release requirements. Automated work must not manufacture a feature to satisfy a daily count.
