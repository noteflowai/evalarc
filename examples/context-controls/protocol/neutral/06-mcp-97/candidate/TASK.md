# Robot recording evidence review

Implement a JSON-lines service that reviews recorded positions and velocities.
Each stdin line is one request. Write exactly one JSON response per request to
stdout; diagnostics belong on stderr. Exit cleanly when stdin reaches EOF.

The input contains an `op` of `review`, a `query_frame`, and a `recording`:

- `source.sha256` identifies the original recorded file. Preserve it in the report.
- `metadata.expected_frames` lists every frame that should be present.
- `metadata.world_from_sensor` describes the coordinate convention.
  For world component `j`, take sensor component `axes[j]`, multiply by
  `signs[j]` and `meters_per_unit`, then add `origin_m[j]` for positions.
  Velocities use the same axis/sign/unit mapping without translation.
- `metadata.clock` defines elapsed seconds as
  `(tick - origin_tick) * seconds_per_tick`.
- `metadata.analytic` gives initial position, initial velocity and constant
  acceleration in world metres and seconds.
- `observations` contains objects with `frame`, `tick`, `position`, and `velocity`.
  Input order is arbitrary. Some expected frames may be absent. The queried frame
  is present. Do not interpolate absent observations.

Return exactly `{"ok": true, "report": {...}}`. The report contains these fields:

| Field | Required value |
| --- | --- |
| `source_sha256` | The provided original source digest |
| `frame` | The requested integer frame |
| `time_seconds` | Its elapsed time, after clock conversion |
| `position_m` | Its three world-coordinate position components |
| `speed_m_s` | Euclidean magnitude of its world velocity |
| `max_position_error_m` | Maximum Euclidean position error across **available** observations against `p0 + v0*t + 0.5*g*t*t` |
| `peak_frame` | Available frame with greatest world z; choose the lowest frame number on an exact tie |
| `peak_height_m` | That frame's world z position |
| `missing_frames` | Sorted list of expected but absent integer frames |

Use JSON numbers for numerical values, never Boolean substitutes, NaN or Infinity.
Checks allow absolute numerical error up to 1e-6 or relative error up to 1e-7.
Do not infer metres, seconds, axis order, or completeness from filenames.

These inputs are derived representations of six real CUDA recordings published
by Robot Reel. Unit, coordinate, clock and omission variants are generated for this
public development task. They are not new physical experiments or hidden test data.
Reporting a source digest provides attribution; it does not authenticate the
original recording's producer.
