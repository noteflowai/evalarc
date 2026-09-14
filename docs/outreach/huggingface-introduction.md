**Download the evidence. Check every gate.** EvalArc 0.8.0 verifies a whole suite from its original TOML, plan, every repetition and attempt, custom acceptance rules and JUnit. It runs offline without a candidate process, Docker, Node or the original candidate directory.

Download **suite-evidence.zip** from the lab and unzip it. `evalarc verify suite-evidence --json` checks all 12 original input files and exits 0 for consistency. Adding `--require-accepted` exits 1: the strict notes gate rejects the faulty policy. Two of three jobs are accepted; only one is fully resolved. Those are separate outcomes.

[Open the evidence lab](https://huggingface.co/spaces/glayguo/evalarc) · [Release 0.8.0](https://github.com/noteflowai/evalarc/releases/tag/v0.8.0) · [Verification workflow and limits](https://github.com/noteflowai/evalarc/blob/main/docs/verification.md)

The public Casebook still provides 167 audit cases, six repeated attempts and three suite jobs. Historical source bytes and scoring rules are unchanged. These are scripted development controls; offline record consistency does not authenticate the producer or independently rerun the grader. Original candidate paths and durations remain reported metadata. EvalArc remains a research preview.

Maintainer update to the existing introduction, developed with AI assistance. Independent community project; no upstream or Hugging Face endorsement is implied.
