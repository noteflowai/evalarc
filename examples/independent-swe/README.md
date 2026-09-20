# Independent-source SWE workflow review

36 recorded Qwen3-8B attempts compare no skill, direct workflow preloading,
actual MCP preloading and an unrelated token-matched MCP preload. Three public
SWE-bench Verified tasks cover Astropy, pytest and SymPy, each with three seeds
per condition. The model ran on an NVIDIA L40S.

No attempt was accepted by the upstream evaluator. **31 have assessable native
test reports; five are marked unavailable for comparison because the upstream
report flags an infrastructure failure.** Eight attempts produced a nonempty
patch. One generation request timed out, leaving that attempt's usage incomplete.
These results do not establish a skill benefit, transport advantage or broad
model capability ranking.

Repeated incorrect file paths account for many failed tool operations. Five
pytest submissions have logs containing both an offline build-dependency
installation failure and candidate-code errors. The upstream label
`network_unreachable` is retained. It is not sufficient evidence that network
access was the sole cause, or that the candidate repair would otherwise pass.
These five reports are not counted as confirmed task rejections.

## Review

Open `index.html` for the condition/task filters, per-attempt trace, patch,
recorded usage and native report. Download `independent-swe.zip` and open
`review/index.html` for an offline version with embedded traces; no server is
required. The archive also includes exact submitted requests, model responses,
command output, context decisions, native logs, six executed upstream controls,
frozen recorder/provider source, dependency identities and input manifests.

Full filesystem tar snapshots, installed dependencies, container images and model
weights are not included. Their recorded identities remain available; image
digests and patches support a separate runtime reconstruction. The archive
supports offline record review without rerunning the model.

Verify the bundle using the accompanying repository:

```bash
python scripts/build_swe_report.py --verify --output examples/independent-swe
```

## Method

The generic skill was frozen before deterministic task selection. The separate
development task was excluded from the 36-attempt cohort. A correction to the
original source-selection account is preserved beside the original protocol;
the exclusions and selected tasks were not changed.

Direct and MCP preloads deliver an identical object. The unrelated object has
the same 444-token length under the pinned tokenizer, and each task's full initial
related/unrelated prompts also match. This is workflow preloading, not autonomous
skill discovery. All conditions share tools, source images and generation limits:
20 turns, 2,048 new tokens per turn, a 900-second interaction budget, and seeds
17, 41 and 97. Conditions rotate within each task/seed block. The fixed runtime
contract describes sampling, context compaction and interruption handling.

The editing container runs as UID 65534, without network, capabilities, host
binds, Docker socket or Git history. Its root is read-only. The trusted host
controller and the separate native grading container have different privileges;
this is not an entirely non-root pipeline.

The six original-defect/upstream-fix controls all completed and produced the
expected native decisions. They validate the environment and parser; they are
not model runs. A declared aggregate-95% rule illustrates how many passing
regression checks can hide an unresolved required defect. Its threshold was
chosen after native-control inspection and before the model cohort. Missing
evidence stays unknown. This is a rule comparison, not a newly discovered
SWE-bench vulnerability.

## Sources and licenses

Dataset: `SWE-bench/SWE-bench_Verified`, revision
`78f471bf655a3137b2e8a75af1501690ec009ec3`. Evaluator:
`SWE-bench/SWE-bench`, commit `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e`.
The model is `Qwen/Qwen3-8B`, revision
`b968826d9c46dd6066d109eabc6255188de91218`.

EvalArc's recorder code is MIT licensed. Source excerpts, upstream patches and
test logs retain the relevant project licenses; the archive includes the
Astropy, pytest and SymPy license texts. Issue text remains attributed to its
upstream public dataset and projects. The evaluator's MIT license is not a
blanket license for every dataset field. Do not relabel this mixed-source
research archive as wholly authored by EvalArc.
