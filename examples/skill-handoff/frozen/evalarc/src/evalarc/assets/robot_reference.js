// Independent JavaScript implementation of the public recording-review contract.
const readline = require("node:readline");

const USE_UNITS = true;
const USE_ORIGIN = true;
const USE_CLOCK = true;
const CHECK_MISSING = true;
const FIND_PEAK = true;
const PRESERVE_SOURCE = true;

function review(request) {
  const recording = request.recording;
  const meta = recording.metadata;
  const frame = meta.world_from_sensor;
  const rows = new Map();
  let peak = null;
  let maximumError = 0;
  for (const raw of recording.observations) {
    const scale = USE_UNITS ? frame.meters_per_unit : 1;
    const position = [0, 1, 2].map((j) =>
      raw.position[frame.axes[j]] * frame.signs[j] * scale +
      (USE_ORIGIN ? frame.origin_m[j] : 0));
    const velocity = [0, 1, 2].map((j) =>
      raw.velocity[frame.axes[j]] * frame.signs[j] * scale);
    const time = USE_CLOCK
      ? (raw.tick - meta.clock.origin_tick) * meta.clock.seconds_per_tick
      : raw.tick;
    const row = { frame: raw.frame, position, velocity, time };
    rows.set(raw.frame, row);
    if (peak === null || position[2] > peak.position[2] ||
        (position[2] === peak.position[2] && raw.frame < peak.frame)) peak = row;
    const delta = position.map((p, j) => p - (
      meta.analytic.position0_m[j] + meta.analytic.velocity0_m_s[j] * time +
      0.5 * meta.analytic.gravity_m_s2[j] * time * time));
    maximumError = Math.max(maximumError, Math.hypot(...delta));
  }
  if (!FIND_PEAK) peak = rows.get(Math.max(...rows.keys()));
  const query = rows.get(request.query_frame);
  return {
    source_sha256: PRESERVE_SOURCE ? recording.source.sha256 : "0".repeat(64),
    frame: query.frame,
    time_seconds: query.time,
    position_m: query.position,
    speed_m_s: Math.hypot(...query.velocity),
    max_position_error_m: maximumError,
    peak_frame: peak.frame,
    peak_height_m: peak.position[2],
    missing_frames: CHECK_MISSING
      ? meta.expected_frames.filter((frame) => !rows.has(frame)).sort((a, b) => a - b)
      : [],
  };
}

const lines = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
lines.on("line", (line) => {
  process.stdout.write(JSON.stringify({ ok: true, report: review(JSON.parse(line)) }) + "\n");
});
