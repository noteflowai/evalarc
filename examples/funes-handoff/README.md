# Funes MCP handoff evidence

Six Qwen3-4B continuations of one public Qwen3-8B program. The selected source, all attempts, generated or unchanged programs, native MCP receipts and independent grades are retained. `preflight/` contains scripted controls, not additional agent trials.

Open index.html offline. Review experiment.json for the preselected order and budgets, model-files.json for reviewed model hashes, and harness/ for the recorder snapshot. Memory embedding/reranking file identities are recorded before and after execution; model weights and the Funes executable are not redistributed.

In an EvalArc source checkout with its development environment, verify this bundle:

```sh
python -m scripts.build_handoff_mcp --verify --output /path/to/this/folder
```

The downloaded ZIP contains records-manifest.json and can be verified after extraction. The hosted manifest.json additionally binds the complete archive's hash. Use the verifier from the source revision associated with the publication.

The verification checks internal consistency, source identities, candidate bytes, independent grading records and derived page content. It does not authenticate the producer or rerun model inference. Public seeds are not hidden tests; exact repeated commands or writes are operation counts, not measured waste or time saved.
