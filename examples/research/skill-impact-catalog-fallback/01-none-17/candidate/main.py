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

    # Convert position and velocity to world coordinates
    position_m = [
        (query_frame_obs["position"][axes[0]] * signs[0] * meters_per_unit) + origin_m[0],
        (query_frame_obs["position"][axes[1]] * signs[1] * meters_per_unit) + origin_m[1],
        (query_frame_obs["position"][axes[2]] * signs[2] * meters_per_unit) + origin_m[2]
    ]
    velocity_m_s = [
        query_frame_obs["velocity"][axes[0]] * signs[0] * meters_per_unit,
        query_frame_obs["velocity"][axes[1]] * signs[1] * meters_per_unit,
        query_frame_obs["velocity"][axes[2]] * signs[2] * meters_per_unit
    ]

    # Calculate speed_m_s
    speed_m_s = (velocity_m_s[0]**2 + velocity_m_s[1]**2 + velocity_m_s[2]**2) ** 0.5

    # Calculate max_position_error_m
    max_position_error_m = 0.0
    for obs in observations:
        frame = obs["frame"]
        if frame in observations_dict:
            obs_position = obs["position"]
            obs_velocity = obs["velocity"]
            obs_time = (obs["tick"] - origin_tick) * seconds_per_tick
            analytic_position = [
                position0_m[0] + velocity0_m_s[0] * obs_time + 0.5 * gravity_m_s2[0] * obs_time**2,
                position0_m[1] + velocity0_m_s[1] * obs_time + 0.5 * gravity_m_s2[1] * obs_time**2,
                position0_m[2] + velocity0_m_s[2] * obs_time + 0.5 * gravity_m_s2[2] * obs_time**2
            ]
            error = ( (obs_position[0] - analytic_position[0])**2 + (obs_position[1] - analytic_position[1])**2 + (obs_position[2] - analytic_position[2])**2 ) ** 0.5
            if error > max_position_error_m:
                max_position_error_m = error

    # Find peak_frame and peak_height_m
    peak_frame = None
    peak_height_m = -float('inf')
    for frame in expected_frames:
        if frame in observations_dict:
            obs_position = observations_dict[frame]["position"]
            z_position = (obs_position[axes[2]] * signs[2] * meters_per_unit) + origin_m[2]
            if z_position > peak_height_m:
                peak_height_m = z_position
                peak_frame = frame
            elif z_position == peak_height_m:
                if peak_frame is None or frame < peak_frame:
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