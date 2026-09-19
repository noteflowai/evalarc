# Recorded input attribution

`robot_recordings.json` preserves the exact JSON text and SHA-256 of six files
from NoteFlow AI's Robot Reel, released under Apache-2.0:

- Repository: https://github.com/noteflowai/robot-reel
- Source commit: `6d9fc525ef443d071ed11b4eefb491b3ca0d0c19`
- Source directory: `docs/solver-lab`
- Files: `genesis-1.json`, `genesis-4.json`, `genesis-16.json`,
  `newton-1.json`, `newton-4.json`, `newton-16.json`
- Copyright: Robot Reel contributors.

The original files describe CUDA float32 ballistic-flight recordings from an
NVIDIA L40S using Genesis 1.4.1 and Newton 1.6.0. EvalArc transforms their
representation and optionally removes samples for review tasks; it does not
relabel these transformations as new simulations.

EvalArc's implementation remains under MIT. The copied recording data remains
under Apache-2.0; the accompanying `ROBOT_DATA_LICENSE.txt` contains that license.
