# Static analysis as an evaluation check

The article's code-based graders include static analysis (lint, type and security
checks) of agent-written code. [`test_static_analysis.py`](test_static_analysis.py)
turns each analyzer into one pytest test with a fixed name; run it once per revision
and compare the JUnit reports with `evalarc diff`:

```bash
python -m pytest examples/static-analysis/test_static_analysis.py \
  --target baseline-output --junitxml static-baseline.xml
python -m pytest examples/static-analysis/test_static_analysis.py \
  --target current-output --junitxml static-current.xml
evalarc diff static-baseline.xml static-current.xml
```

`diff` exits 1 when an analyzer that passed on the baseline fails on the current
revision, and an analyzer that is not installed is skipped on both sides (`mypy`,
`bandit`). `tests/test_static_analysis_example.py` runs exactly this on two small
generated folders in CI.

Feeding a linter's own JUnit output (`ruff check --output-format junit`) to `evalarc
diff` does not work as a gate. Its testcases are keyed by rule and absolute file path,
not by violation. A second violation of a rule that already fires in the same file is
only another failing attempt of the same check, so the gate misses it; moving the code
to another folder, or fixing the last violation of a rule (which removes its testcase),
fails the gate without any new problem. Keep one
stable check per analyzer instead, or run the analyzer as an `eval-init` `command`
check.
