# Persistent-request follow-up

This six-trial cohort was planned after all six initial controls failed at the response protocol. It preserves the same Qwen3-8B revision, Skills Anywhere built library, skill texts, 476-token tool-result payloads, task, model seeds, evaluation seeds, tools and budgets. It adds the same protocol_probe.py and an instruction to flush responses to both conditions. The two cohorts are separate public-development observations, not a held-out efficacy estimate.

The relevant condition produced three programs scoring 87.5%, each with four numerical-metric case failures out of eight cases. None resolved the full task. Each unrelated-text condition called finish without writing the program; all three received zero. The probe only checks JSONL interaction and does not grade numerical answers. The full messages, source, actual tool results and independent evaluations remain available.

The experiment plan and exact harness were saved before inference. No attempt was retried or removed. The protocol helper was separately checked inside the same Docker workspace: the reference returned both responses, while a buffered control timed out. The helper and its original SHA-256 are recorded for every trial.

See the collection README for commands that use these archived harness, library and dependency files. A local GPU is needed to repeat inference; ordinary Python can verify the saved evaluation and publication artifacts. Candidate execution uses the bounded Docker runtime. These records do not establish general skill efficacy, a model ranking or unseen-fault coverage.
