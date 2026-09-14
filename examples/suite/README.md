# Recorded suite · v0.5

This is a real Docker execution of the
[partial-progress configuration](../suites/partial-progress.toml), recorded on
2026-09-14. It contains 5 attempts and 31 case executions across coding and
simulated support workflows. The CLI intentionally returned exit code 1.

| Job | Mean task score | Resolved attempts | Gate |
| --- | ---: | ---: | --- |
| `coding-reference` | 1.0 | 1/1 | Accepted: default full-resolution rule |
| `support-partial` | 0.9375 | 0/2 | Accepted: explicit partial-progress thresholds |
| `support-protected` | 0.9375 | 0/2 | Rejected: every notes check must pass |

Both support jobs use the same frozen defective policy and produce the same
underlying check outcomes. A gate changes the suite's acceptance decision, not
the task's scores or resolution flag.

Open [the suite report](index.html), [JUnit](junit.xml), or
[complete suite JSON](suite.json). Each job links to every attempt's full JSON,
HTML, and host progress events. The original manifest bytes and resolved plan
are retained. Resolved paths in `plan.json` identify the temporary validation
workspace; follow the [setup instructions](../suites/README.md) to reproduce
the candidates and run the configuration in your own checkout.

These are scripted controls on public development cases. No model API, real
helpdesk service, statistical generalization claim, or hosted CI importer was
involved.
