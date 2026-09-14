I'm publishing EvalArc as its maintainer: an open toolkit for auditing the
graders behind AI-agent evaluations.

Start with the support-tools example in this Space. A scripted policy earns
**93.75%**, yet fails acceptance because a retry duplicates an already committed
note. Step through the failed response and retry, then select the reference to
see an idempotent receipt without a second state change.

The coding example shows a different gap: **92.5%**, but a compare-and-swap
operation treats JSON `true` and `1` as equal. Both examples expose the failed
check instead of hiding it behind an aggregate score.

The lab includes two task packs, 15 declared faulty implementations, their
known-good references, and downloadable JSON with reproduction fingerprints.
It replays recorded Docker audits. No model is called in the Space.

- [Source and quickstart](https://github.com/noteflowai/evalarc)
- [Chinese introduction](https://github.com/noteflowai/evalarc/blob/main/README.zh-CN.md)
- [Methodology and limits](https://github.com/noteflowai/evalarc/blob/main/docs/methodology.md)

This is an MIT-licensed research preview with public development tasks and
scripted controls. It does not establish frontier-model performance, arbitrary
reward-hack resistance or RL gains.

Feedback is welcome on plausible defects the current controls miss, clearer
task contracts, and independent reference implementations. A small reproducible
case is especially useful.
