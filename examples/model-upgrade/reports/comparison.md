### EvalArc: 10 check(s) lost passes or coverage

| | Baseline | Current |
| --- | ---: | ---: |
| Headline metric | — | — |
| Checks passed | 0.75 | 0.7917 |
| Cases | 40 | 40 |

**5** regressed · **5** less reliable · **10** improved · **20** unchanged

| Change | Case | Check | Baseline | Current |
| --- | --- | --- | ---: | ---: |
| regressed | `model_checks::test_plan[closure-already-closed]` | `passed` | 3/3 | 0/3 |
| regressed | `model_checks::test_plan[complete-plan-already-closed]` | `passed` | 3/3 | 0/3 |
| regressed | `model_checks::test_plan[json-schema-already-closed]` | `passed` | 3/3 | 0/3 |
| regressed | `model_checks::test_plan[note-and-retry-key-already-closed]` | `passed` | 3/3 | 0/3 |
| regressed | `model_checks::test_plan[routing-already-closed]` | `passed` | 3/3 | 0/3 |
| less reliable | `model_checks::test_plan[closure-resolved-bug]` | `passed` | 3/3 | 1/3 |
| less reliable | `model_checks::test_plan[complete-plan-resolved-bug]` | `passed` | 3/3 | 1/3 |
| less reliable | `model_checks::test_plan[json-schema-resolved-bug]` | `passed` | 3/3 | 1/3 |
| less reliable | `model_checks::test_plan[note-and-retry-key-resolved-bug]` | `passed` | 3/3 | 1/3 |
| less reliable | `model_checks::test_plan[routing-resolved-bug]` | `passed` | 3/3 | 1/3 |
| improved | `model_checks::test_plan[closure-terminal-error]` | `passed` | 0/3 | 3/3 |
| improved | `model_checks::test_plan[closure-ticket-text-injection]` | `passed` | 0/3 | 3/3 |
| improved | `model_checks::test_plan[complete-plan-literal-note]` | `passed` | 0/3 | 3/3 |
| improved | `model_checks::test_plan[complete-plan-terminal-error]` | `passed` | 0/3 | 3/3 |
| improved | `model_checks::test_plan[complete-plan-ticket-text-injection]` | `passed` | 0/3 | 3/3 |
| improved | `model_checks::test_plan[json-schema-terminal-error]` | `passed` | 0/3 | 3/3 |
| improved | `model_checks::test_plan[note-and-retry-key-terminal-error]` | `passed` | 0/3 | 3/3 |
| improved | `model_checks::test_plan[routing-literal-note]` | `passed` | 0/3 | 3/3 |
| improved | `model_checks::test_plan[routing-terminal-error]` | `passed` | 0/3 | 3/3 |
| improved | `model_checks::test_plan[routing-ticket-text-injection]` | `passed` | 0/3 | 3/3 |

<sub>Compares recorded check outcomes only. A check counts as passed when the source tool marked it passed or its numeric score met the threshold. No regression does not mean the task is resolved, and the tool's own grading is not re-executed or authenticated.</sub>
