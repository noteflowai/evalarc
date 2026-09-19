"""Independent Python implementation of the public recording-review contract."""

import json
import math
import sys

USE_UNITS = True
USE_ORIGIN = True
USE_CLOCK = True
CHECK_MISSING = True
FIND_PEAK = True
PRESERVE_SOURCE = True


def review(request):
    recording = request["recording"]
    metadata = recording["metadata"]
    mapping = metadata["world_from_sensor"]
    clock = metadata["clock"]
    scale = mapping["meters_per_unit"] if USE_UNITS else 1
    converted = []
    for sample in recording["observations"]:
        p, v = [], []
        for axis, sign, origin in zip(mapping["axes"], mapping["signs"], mapping["origin_m"]):
            p.append(sample["position"][axis] * sign * scale + (origin if USE_ORIGIN else 0))
            v.append(sample["velocity"][axis] * sign * scale)
        t = (sample["tick"] - clock["origin_tick"]) * clock["seconds_per_tick"]
        if not USE_CLOCK:
            t = sample["tick"]
        converted.append({"frame": sample["frame"], "position": p, "velocity": v, "time": t})
    query = next(row for row in converted if row["frame"] == request["query_frame"])
    analytic = metadata["analytic"]
    errors = []
    for row in converted:
        ideal = [
            analytic["position0_m"][axis]
            + analytic["velocity0_m_s"][axis] * row["time"]
            + analytic["gravity_m_s2"][axis] * row["time"] ** 2 / 2
            for axis in range(3)
        ]
        errors.append(math.sqrt(sum((a - b) ** 2 for a, b in zip(ideal, row["position"]))))
    peak = sorted(converted, key=lambda row: (-row["position"][2], row["frame"]))[0]
    if not FIND_PEAK:
        peak = max(converted, key=lambda row: row["frame"])
    seen = {row["frame"] for row in converted}
    return {
        "source_sha256": recording["source"]["sha256"] if PRESERVE_SOURCE else "0" * 64,
        "frame": query["frame"],
        "time_seconds": query["time"],
        "position_m": query["position"],
        "speed_m_s": math.sqrt(sum(value * value for value in query["velocity"])),
        "max_position_error_m": max(errors),
        "peak_frame": peak["frame"],
        "peak_height_m": peak["position"][2],
        "missing_frames": sorted(set(metadata["expected_frames"]) - seen) if CHECK_MISSING else [],
    }


for line in sys.stdin:
    print(json.dumps({"ok": True, "report": review(json.loads(line))}, allow_nan=False), flush=True)
