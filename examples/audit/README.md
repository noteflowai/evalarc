# Recorded development audit

`audit.json` and `index.html` were generated on 2026-09-14 from the v0.1.0
implementation using Docker and seed 17:

```bash
graderail audit --seeds 17 --output examples/audit
```

The development machine required the Docker CLI wrapper `sudo -n docker`;
the grading container still ran as UID/GID 65534 with the documented
restrictions. No LLM or external inference service was used.

The positive control passed all 15 cases. All eight declared faults were
detected in their target dimensions. These are scripted controls, not model
submissions. Case durations reflect this machine and include container
startup/cleanup; they are not portable performance measurements.

See the JSON for exact hashes and runtime settings, and
[validation](../../docs/validation.md) for the remaining verification.
