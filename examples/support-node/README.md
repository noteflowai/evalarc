# JavaScript support policy

This independent, dependency-free Node.js policy uses the same tool protocol
and host verifier as the Python reference.

From the repository root, with Node.js installed:

```bash
evalarc evaluate examples/support-node --task support-routing \
  --backend local --trust-local --output runs/support-node
```

The `evalarc.toml` manifest replaces the default Python launch command. Arguments
are executed directly without a shell. The task is selected by the evaluator's
`--task`, not by candidate-controlled configuration.

Local execution uses a minimal environment with the system executable search
path. If Node is installed elsewhere (for example, by a version manager or
`actions/setup-node`), set the first manifest argument to its absolute path,
as reported by `command -v node`. CI copies the example into a temporary
workspace and records that absolute command in the evaluation metadata.

For Docker execution supply an image containing Node with `--image`. The default
Python image does not contain Node. No automatic dependency installation occurs.
