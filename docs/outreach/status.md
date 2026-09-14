# Publication log

Verified on 2026-09-14. The project was previously local-only. Source, the
interactive evidence lab, and maintainer announcements are now public.

| Channel | Status |
| --- | --- |
| [GitHub source](https://github.com/noteflowai/evalarc) | Public; source and deployment CI passed |
| [GitHub releases](https://github.com/noteflowai/evalarc/releases) | v0.4.0 research preview published; wheel, source archive and checksums verified by anonymous download |
| [GitHub Pages](https://noteflowai.github.io/evalarc/) | Live; desktop and mobile checks passed |
| [Hugging Face Space](https://huggingface.co/spaces/glayguo/evalarc) | v0.4 public; actual Hub iframe checked on desktop and mobile |
| [Hugging Face introduction](https://huggingface.co/spaces/glayguo/evalarc/discussions/1) | Existing title and body updated for v0.4; readback matched |
| [NoteFlow AI collection](https://huggingface.co/collections/glayguo/noteflow-ai-open-source-playgrounds-6aa693c382b0184786eb8856) | Entry updated with the six-attempt v0.4 example; readback matched |
| [科技爱好者周刊 #11671](https://github.com/ruanyf/weekly/issues/11671) | Existing submission updated for v0.4; open, awaiting editorial review |
| [HelloGitHub #3698](https://github.com/521xueweihan/HelloGitHub/issues/3698) | Existing description and screenshot updated for v0.4; open, awaiting editorial review |
| [X maintainer launch](https://x.com/glay_oneai/status/2099338382518399269) | Overview and three project replies verified in the published conversation; the EvalArc reply describes the v0.3 comparison |

The weekly README explicitly invites software submissions through issues.
HelloGitHub's project template welcomes self-recommendations and requires an
original description of 32–256 characters. Rules were checked on 2026-09-14.

Before submission, GitHub issue searches found no prior EvalArc/GradeRail
recommendation in either project. The HelloGitHub website search also showed
no EvalArc result and its project-specific page returned 404. Original
community-specific descriptions disclosed maintainer affiliation, the
scripted-control scope, and the absence of model or RL results.

Editorial submissions are not acceptance or endorsement. No PyPI publication,
paid promotion, model-provider integration or third-party endorsement is
claimed. The customer description is in [launch materials](launch.md).

The first complete publication came from source `0941fde4d452fff257f2627c9bc5e27a9bf85afc`
and [CI run 34797722807](https://github.com/noteflowai/evalarc/actions/runs/34797722807).
Later builds identify their exact source in each site's `manifest.json`;
the workflow publishes only the artifact that passed its checks.

## v0.3 publication · 2026-09-14

[PR #1](https://github.com/noteflowai/evalarc/pull/1) integrated the completed
workflow update and the new comparison showcase. All checks passed before
merge. [Main CI run 34801187828](https://github.com/noteflowai/evalarc/actions/runs/34801187828)
then passed and deployed source `67dc748067251b96160f49f390eaf8792d8563ed`.
The [v0.3.0 release](https://github.com/noteflowai/evalarc/releases/tag/v0.3.0)
uses that source.

The website bundle contains 18 files including its manifest. Public Pages and
the actual Hugging Face iframe passed checks at 1440 px and 390 px: 17 audit
implementations, 167 audit cases, three comparison cases and two standalone
report types. The release's wheel, source archive and checksum file were
downloaded without authentication and matched to the built artifacts.

Existing announcements and submissions were updated in place. No duplicate
editorial issues were opened. This remains maintainer promotion and pending
editorial review, not third-party acceptance.

## v0.4 publication · 2026-09-14

The local functional update `ca1cf5180aeab08518410982ce07ab26e0232e93`
adds frozen-candidate repetition, total case deadlines and bounded diagnostics.
The publication update exposes the preserved reference repetition and a new
three-attempt Docker recording of the duplicate-write control. Both reuse
the same cases, grader and immutable image. Every attempt remains downloadable;
the build recomputes summaries and rejects altered or missing evidence.

Local validation passed 123 Python tests, lint, formatting, both Docker audits
and the desktop/mobile evidence explorer. The earlier comparison remains a
historical v0.3 record. Publication uses the same guarded CI workflow and
existing maintainer discussions; no new editorial submission is needed.

[PR #2](https://github.com/noteflowai/evalarc/pull/2) passed all checks and
merged as `7de84f7eecb1da685fbdeab30e05aa92f76dc709`.
[Main CI run 34803983711](https://github.com/noteflowai/evalarc/actions/runs/34803983711)
passed and deployed its 36-file artifact to Pages and Hugging Face.
Both public manifests identified that source, and the actual public Pages and
Hub iframe passed the desktop/mobile checks, including all six attempts.

The [v0.4.0 release](https://github.com/noteflowai/evalarc/releases/tag/v0.4.0)
uses the merge commit. Its wheel was installed in a clean environment and
exercised outside the checkout: readiness passed; the repeated faulty control
returned exit 1, mean 0.9375 and zero resolved attempts. Wheel, source archive
and `SHA256SUMS` were downloaded anonymously and matched the built assets.

The existing HF discussion, collection entry and both Chinese submissions
were updated in place and read back. The editorial issues remain open;
neither acceptance nor external endorsement is claimed. The X launch consists
of its verified overview and three project replies, including the historical
v0.3 EvalArc example.
