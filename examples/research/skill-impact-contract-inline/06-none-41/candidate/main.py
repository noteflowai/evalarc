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

    # Calculate time_seconds for the query frame
    query_frame_obs = observations_dict[query_frame]
    tick = query_frame_obs["tick"]
    time_seconds = (tick - origin_tick) * seconds_per_tick

    # Calculate position_m for the query frame
    position_m = [
        (position_m_component * signs[i] * meters_per_unit) + origin_m[i]
        for i, position_m_component in enumerate(observations_dict[query_frame]["position"])]

    # Calculate speed_m_s for the query frame
    velocity_m = [
        velocity_m_component * signs[i] * meters_per_unit
        for i, velocity_m_component in enumerate(observations_dict[query_frame]["velocity"])]
    speed_m_s = sum(vel ** 2 for vel in velocity_m) ** 0.5

    # Calculate max_position_error_m
    max_position_error_m = 0.0
    for obs in observations:
        frame = obs["frame"]
        if frame in observations_dict:
            obs_position = obs["position"]
            obs_position_m = [
                (pos_component * signs[i] * meters_per_unit) + origin_m[i]
                for i, pos_component in enumerate(obs_position)]
            t = (obs["tick"] - origin_tick) * seconds_per_tick
            analytic_position = [
                position0_m[i] + velocity0_m_s[i] * t + 0.5 * gravity_m_s2[i] * t ** 2
                for i in range(3)]
            error = sum((obs_pos - analytic_pos) ** 2 for obs_pos, analytic_pos in zip(obs_position_m, analytic_position)) ** 0.5
            if error > max_position_error_m:
                max_position_error_m = error

    # Find peak_frame and peak_height_m
    peak_frame = None
    peak_height_m = -float('inf')
    for frame in expected_frames:
        if frame in observations_dict:
            obs_position = observations_dict[frame]["position"]
            obs_position_m = [
                (pos_component * signs[i] * meters_per_unit) + origin_m[i]
                for i, pos_component in enumerate(obs_position)]
            z_position = obs_position_m[2]
            if z_position > peak_height_m:
                peak_height_m = z_position
                peak_frame = frame
            elif z_position == peak_height_m and frame < peak_frame:
                peak_frame = frame

    # Find missing_frames
    missing_frames = [frame for frame in expected_frames if frame not in observations_dict]
    missing_frames.sort()

    # Prepare the report
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
