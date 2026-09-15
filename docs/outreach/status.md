# Publication log

## 2026-09-15 research note to the hack-verifiable environments authors

Submitted [issue #4](https://github.com/MajoRoth/hack-verifiable-environments/issues/4) on the
maintainer's explicit instruction, and included EvalArc in a finding-led thread from
[@glay_oneai](https://x.com/glay_oneai/status/2099745359224578381).

The note states the correspondence and where it stops. HVE plants a hack in the environment and
measures whether the agent exploits it; an audit here plants a fault in the submission and measures
whether the checks catch it. It says twice that EvalArc is not an HVE implementation and does not
measure reward hacking.

The substance is the assumption their measurement rests on. An exploitation rate is meaningful
because a planted hack is detectable by construction, and the grader-side measurement puts a number
on that: 21 of 21 declared faults detected at a mutation score of 1.0, with six of the twenty-one
caught by exactly one case each. It asks a question back, whether a planted hack's own detection
margin is worth reporting beside the hacking rate, and volunteers the implementation error that
produced a wrong number first, namely counting case runs instead of distinct cases.

Numbers were re-verified against the current main before submission rather than copied from an
earlier session: 8/8, 7/7 and 6/6, three plus two plus one single-case detections, weakest margin
one in every pack. No link, citation or mention was requested; the issue offers to move to a
discussion thread or email rather than duplicate itself. Nothing is claimed about the authors'
agreement.


## 0.8.0 suite handoff publication · 2026-09-14

[PR #8](https://github.com/noteflowai/evalarc/pull/8) added offline verification
of original suite TOML, plan, every attempt, custom gates and JUnit, plus a
12-file evidence ZIP download. Main commit
`e9cba3c5db80411ffee35fe2568fee23a74997da` passed all 254 tests on Python
3.11–3.13, four Docker task/language audits, browser checks and deployment
[CI](https://github.com/noteflowai/evalarc/actions/runs/34817758768).

The 0.8.0 research preview includes wheel, source archive, evidence ZIP and
SHA256SUMS. All four assets matched anonymous downloads. The final wheel
passed offline verification outside the checkout with empty PATH, including
modified-JUnit rejection. The archive preserves all original evidence bytes.

Anonymous readback checked the Space's 61 manifest entries and the Casebook's
31 entries against their recorded hashes and release source commit. The actual
Hub iframe passed 1440/390/320px checks, including ZIP download and its manifest
hash. Consistency, configured acceptance and full resolution remain separate.

The existing HF introduction, collection note, weekly submission and HelloGitHub
submission were updated and read back exactly. Both editorial issues remain
open with no comments. No new issue, reminder comment or X post was created;
no PyPI publication was made. [Publication receipts](publication-0.8.0.json).


## 0.7.1 UI publication · 2026-09-14

[Release 0.7.1](https://github.com/noteflowai/evalarc/releases/tag/v0.7.1) is public.
[Release validation](https://github.com/noteflowai/evalarc/actions/runs/34813660899) passed;
the real Hugging Face iframe was exercised at 1440, 390 and 320 pixels.
Exact case/step links, keyboard case return, bounded network requests and independent retries are public. Original evidence is unchanged. The attached wheel and source archive matched anonymous downloads, and the installed wheel passed offline checks with an empty PATH.

The existing weekly and HelloGitHub submissions and HF introduction were rewritten around the current workflow, then read back exactly. Both editorial submissions remain open with no comments; no new issue or reminder comment was created. The existing five-item HF collection was updated. [Publication receipts](publication-0.7.1.json).

Earlier publication history follows.

Verified on 2026-09-14. The project was previously local-only. Source, the
interactive evidence lab, and maintainer announcements are now public.

| Channel | Status |
| --- | --- |
| [GitHub source](https://github.com/noteflowai/evalarc) | Public; source and deployment CI passed |
| [GitHub releases](https://github.com/noteflowai/evalarc/releases) | v0.8.0 research preview published; wheel, source archive, evidence ZIP and checksums verified by anonymous download |
| [GitHub Pages](https://noteflowai.github.io/evalarc/) | Live; desktop and mobile checks passed |
| [Hugging Face Space](https://huggingface.co/spaces/glayguo/evalarc) | v0.8.0 public; guarded deployment, anonymous file verification and actual desktop/mobile Hub iframe checks passed |
| [Hugging Face Casebook](https://huggingface.co/datasets/glayguo/evalarc-casebook) | Public dataset; all 31 manifest entries and every row read back anonymously; actual table checked on desktop and mobile |
| [Hugging Face introduction](https://huggingface.co/spaces/glayguo/evalarc/discussions/1) | Existing title and body updated for v0.8.0 suite handoff verification; readback matched |
| [NoteFlow AI collection](https://huggingface.co/collections/glayguo/noteflow-ai-open-source-playgrounds-6aa693c382b0184786eb8856) | Now contains three project Spaces and two evidence datasets; Casebook entry and v0.8.0 Space note verified |
| [科技爱好者周刊 #11671](https://github.com/ruanyf/weekly/issues/11671) | Existing submission updated for v0.8.0 and the Casebook; open, awaiting editorial review |
| [HelloGitHub #3698](https://github.com/521xueweihan/HelloGitHub/issues/3698) | Existing description updated for v0.8.0 and the Casebook; open, awaiting editorial review |
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

## v0.5 publication · 2026-09-14

The completed local update `fb5d943f58e9f75f107fbf58e793c47c7d190abc`
adds declarative TOML suites, frozen candidate inputs, explicit per-job
acceptance gates and JUnit export. It was merged with the v0.4 publication
work. The new suite explorer shows the same 93.75% score and 0/2 fully
resolved attempts under two different gates: the deliberately permissive
rule accepts partial progress; the rule requiring every notes check rejects
it. Configured acceptance and full task resolution remain separate.

[PR #3](https://github.com/noteflowai/evalarc/pull/3) passed all checks and
merged as `6cc9a65f4d9f2fd956ff315779e5f8cbadb09af7`.
[Main CI run 34805035857](https://github.com/noteflowai/evalarc/actions/runs/34805035857)
passed all eight jobs and deployed the same verified 61-file bundle to
Pages and Hugging Face. Public manifests identified that source and a clean
checkout. The actual Pages site and Hub iframe passed at 1440 px and 390 px:
17 audit implementations, 167 audit cases, three comparison cases, six
repetition attempts, five suite attempts and seven offline report paths.
The downloaded JUnit contains three tests, one expected failure and zero errors.

Local validation passed 172 Python tests, lint, formatting and two fresh
Docker suites with 54 case executions. The acceptance suite exits 0; the
partial-progress suite exits 1 as intended. The build recomputes gates from
the original TOML and all attempt records and checks JUnit semantics.
Tests reject altered gate decisions and failures relabeled as environment errors.
The standalone suite report remains reachable if interactive data loading fails.

The [v0.5.0 release](https://github.com/noteflowai/evalarc/releases/tag/v0.5.0)
uses the merge commit. The final wheel was installed in a clean environment
and exercised outside the checkout: its dry run planned five attempts and
31 case executions, and its Docker run retained the expected rejected gate
and JUnit result. The source archive matches the final source. Wheel, source
archive and checksums were downloaded anonymously and matched the built assets.

The existing HF introduction, collection entry and both Chinese submissions
were updated for v0.5 and read back successfully. The editorial issues remain
open with no acceptance recorded. The existing X launch remains published;
its EvalArc reply describes the historical v0.3 comparison, and the linked
Space now includes the v0.5 showcase. No extra launch posts were sent.

These are scripted development controls. No hosted CI importer, live model
performance or reliability on unseen tasks was validated by this publication.

## Casebook publication · 2026-09-14

[PR #4](https://github.com/noteflowai/evalarc/pull/4) added a reproducible
dataset export and guarded automatic publication. Its merge
`f33a170500076386833e26224415bfa665da5d40` passed
[main CI 34807756249](https://github.com/noteflowai/evalarc/actions/runs/34807756249).
The initial public Hub revision was
`1539990bde4b2c73d3a10d3c0c86c24b80687b0f`.

The [Casebook](https://huggingface.co/datasets/glayguo/evalarc-casebook) separates
167 audit cases, six repeated attempts and three suite jobs into development
configurations. Their row units differ and must not be added as independent
trials. Every row retains an exact source-file pointer, hash and code revision.
The 32-file export includes unchanged evidence, suite configuration and JUnit.

All exported files were downloaded without credentials and verified. The
public `datasets` reader matched every local row. HF's initial `ResponseNotReady`
state cleared; its API then listed all three configurations without pending
or failed entries, and the actual table displayed both support outcomes at
1440 px and 390 px. The first four columns expose identity, mean score,
gate acceptance and full resolution. The dataset was added once to the
existing NoteFlow AI collection and read back.

## v0.6 publication · 2026-09-14

The external functional update
`204df87` adds JavaScript starters, independent references and audit controls.
It was preserved and merged with the completed Casebook work in
[PR #5](https://github.com/noteflowai/evalarc/pull/5), without text conflicts.
The combined tree passed 210 Python tests, lint, formatting and desktop/mobile
site checks. A fresh mixed-language Docker suite resolved all three jobs.
All archived JavaScript audit evaluations were independently validated.

The merge `eed29f4f596cde74b797a2fb1e354a87e5adf2aa` passed all ten jobs in
[main CI 34808296273](https://github.com/noteflowai/evalarc/actions/runs/34808296273),
including the four task/language Docker audits, Pages and HF publication.
The [v0.6.0 research preview](https://github.com/noteflowai/evalarc/releases/tag/v0.6.0)
uses that source.

The final wheel was installed in a fresh environment outside the checkout.
Readiness passed; the Docker suite retained 34 case executions, three fully
resolved jobs and JUnit with three tests, zero failures and zero errors.
All JavaScript assets and the source archive matched the release tree.
Wheel, source archive and checksum file were downloaded anonymously and
matched the built artifacts. The public Pages site passed desktop/mobile checks.
The actual Hub iframe also passed both widths on retry. The first navigation
timed out waiting for the outer page to become network-idle; the successful
retry reported no application errors.

The v0.6 dataset revision
`f98f4fb011f1b9e3e9b38be23bb58f3e2ff36046` identified the same merge commit;
all 32 files and all rows were verified again against its source artifact.
The Casebook retains the earlier recordings and does not relabel them as
v0.6 language comparisons.

The existing HF introduction, collection Space note and both Chinese
submissions now describe v0.6 and the Casebook. Exact readbacks matched.
The editorial issues remain open with no comments; no duplicate issues,
reminder comments or new X posts were sent. The established X overview and
three replies remain the launch thread for all three projects.

## v0.7 publication · 2026-09-14

[PR #6](https://github.com/noteflowai/evalarc/pull/6) added the offline
`evalarc verify` workflow. Main commit
`5363087d9b46d180d3068cf3d994b3c3eff571b6` passed all ten
[CI jobs](https://github.com/noteflowai/evalarc/actions/runs/34811075628),
including Python 3.11–3.13, all four Docker task/language audits, site tests,
Pages and verified HF publication. The 229 tests include nineteen new
verification cases. The exact wheel additionally passed the installed check
outside the checkout with an empty PATH.

The [0.7.0 research preview](https://github.com/noteflowai/evalarc/releases/tag/v0.7.0)
is public. All three assets were downloaded anonymously and matched:

| Asset | SHA-256 |
| --- | --- |
| Wheel | `91038a38ec7df0f70b240184826ce4918843a7090001015109840f21b9c1fe34` |
| Source archive | `dd963aa7def7c4a57f6e926b52d17bf16e265c8c0f13e9342a6d626afcdcdcf3` |
| SHA256SUMS | `ace1859a520d21472eac8edbd4e978d39513ba57d3fb865b70f64da4be54981a` |

The existing weekly and HelloGitHub submissions, HF introduction and collection
note were updated in place and exact readbacks matched. Both editorial
submissions remain open with no comments. The HF Casebook retains the same
historical controls; publishing the verifier does not create new model results.
[Verification scope](../verification.md) explicitly distinguishes consistency,
resolution, a grader rerun, and suite-level gate checks. No new X post or PyPI
publication was made.
