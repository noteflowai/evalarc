"""Implement the recording-review contract described in TASK.md."""

import json
import sys


def review(request):
    # Extract the query frame
    query_frame = request["query_frame"]
    recording = request["recording"]
    source_sha256 = recording["source"]["sha256"]
    metadata = recording["metadata"]
    observations = recording["observations"]

    # Process metadata
    expected_frames = metadata["expected_frames"]
    world_from_sensor = metadata["world_from_sensor"]
    axes = world_from_sensor["axes"]
    signs = world_from_sensor["signs"]
    origin_m = world_from_sensor["origin_m"]
    meters_per_unit = world_from_sensor["meters_per_unit"]
    clock = metadata["clock"]
    origin_tick = clock["origin_tick"]
    seconds_per_tick = clock["seconds_per_tick"]
    analytic = metadata["analytic"]
    position0_m = analytic["position0_m"]
    velocity0_m_s = analytic["velocity0_m_s"]
    gravity_m_s2 = analytic["gravity_m_s2"]

    # Process observations
    observations_dict = {obs["frame"]: obs for obs in observations}
    available_frames = sorted(observations_dict.keys())

    # Calculate time_seconds for the query frame
    query_tick = observations_dict[query_frame]["tick"]
    time_seconds = (query_tick - origin_tick) * seconds_per_tick

    # Calculate position_m for the query frame
    query_position = observations_dict[query_frame]["position"]
    position_m = [
        query_position[axes[0]] * signs[0] * meters_per_unit + origin_m[0],
        query_position[axes[1]] * signs[1] * meters_per_unit + origin_m[1],
        query_position[axes[2]] * signs[2] * meters_per_unit + origin_m[2]
    ]

    # Calculate speed_m_s for the query frame
    query_velocity = observations_dict[query_frame]["velocity"]
    speed_m_s = (query_velocity[axes[0]] ** 2 + query_velocity[axes[1]] ** 2 + query_velocity[axes[2]] ** 2) ** 0.5

    # Calculate max_position_error_m
    max_position_error_m = 0.0
    for frame in available_frames:
        obs = observations_dict[frame]
        tick = obs["tick"]
        position = obs["position"]
        # Convert position to world coordinates
        world_position = [
            position[axes[0]] * signs[0] * meters_per_unit + origin_m[0],
            position[axes[1]] * signs[1] * meters_per_unit + origin_m[1],
            position[axes[2]] * signs[2] * meters_per_unit + origin_m[2]
        ]
        # Calculate expected position using analytic model
        t = (tick - origin_tick) * seconds_per_tick
        expected_position = [
            position0_m[0] + velocity0_m_s[0] * t + 0.5 * gravity_m_s2[0] * t ** 2,
            position0_m[1] + velocity0_m_s[1] * t + 0.5 * gravity_m_s2[1] * t ** 2,
            position0_m[2] + velocity0_m_s[2] * t + 0.5 * gravity_m_s2[2] * t ** 2
        ]
        # Calculate position error
        error = (world_position[0] - expected_position[0]) ** 2 + (world_position[1] - expected_position[1]) ** 2 + (world_position[2] - expected_position[2]) ** 2
        error = error ** 0.5
        if error > max_position_error_m:
            max_position_error_m = error

    # Find peak_frame and peak_height_m
    peak_frame = None
    peak_height_m = -float('inf')
    for frame in available_frames:
        obs = observations_dict[frame]
        position = obs["position"]
        # Convert position to world coordinates
        world_position = [
            position[axes[0]] * signs[0] * meters_per_unit + origin_m[0],
            position[axes[1]] * signs[1] * meters_per_unit + origin_m[1],
            position[axes[2]] * signs[2] * meters_per_unit + origin_m[2]
        ]
        if world_position[2] > peak_height_m:
            peak_height_m = world_position[2]
            peak_frame = frame
        elif world_position[2] == peak_height_m:
            if frame < peak_frame:
                peak_frame = frame

    # Find missing_frames
    missing_frames = []
    for frame in expected_frames:
        if frame not in observations_dict:
            missing_frames.append(frame)
    missing_frames.sort()

    # Create report
    report = {
        "source_sha256": source_sha256,
        "frame": query_frame,
        "time_seconds": time_seconds,
        "position_m": position_m,
        "speed_m_s": speed_m_s,
        "max_position_error_m": max_position_error_m,
        "peak_frame": peak_frame,
        "peak_height_m": peak_height_m,
        "missing_frames": missing_frames
    }
    return report


for line in sys.stdin:
    print(json.dumps({"ok": True, "report": review(json.loads(line))}), flush=True)
