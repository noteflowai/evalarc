"""Implement the recording-review contract described in TASK.md."""

import json
import sys
import math


def review(request):
    # Extract the required data from the request
    source_sha256 = request.get('source.sha256')
    query_frame = request.get('query_frame')
    recording = request.get('recording')
    metadata = recording.get('metadata')
    observations = recording.get('observations')

    # Extract metadata details
    expected_frames = metadata.get('expected_frames', [])
    world_from_sensor = metadata.get('world_from_sensor', [])
    signs = world_from_sensor.get('signs', [])
    meters_per_unit = world_from_sensor.get('meters_per_unit', 1.0)
    origin_m = world_from_sensor.get('origin_m', [0.0, 0.0, 0.0])
    clock = metadata.get('clock', {})
    origin_tick = clock.get('origin_tick', 0)
    seconds_per_tick = clock.get('seconds_per_tick', 1.0)
    analytic = metadata.get('analytic', {})
    p0 = analytic.get('p0', [0.0, 0.0, 0.0])
    v0 = analytic.get('v0', [0.0, 0.0, 0.0])
    g = analytic.get('g', [0.0, 0.0, 0.0])

    # Process observations
    observation_data = []
    for obs in observations:
        frame = obs.get('frame')
        tick = obs.get('tick')
        position = obs.get('position', [0.0, 0.0, 0.0])
        velocity = obs.get('velocity', [0.0, 0.0, 0.0])
        observation_data.append((frame, tick, position, velocity))

    # Find missing frames
    missing_frames = [frame for frame in expected_frames if not any(obs[0] == frame for obs in observation_data)]
    missing_frames.sort()

    # Find the queried frame's data
    queried_frame_data = None
    for obs in observation_data:
        if obs[0] == query_frame:
            queried_frame_data = obs
            break

    # Calculate time_seconds for the queried frame
    time_seconds = (queried_frame_data[1] - origin_tick) * seconds_per_tick

    # Convert position and velocity to world coordinates
    position_m = [
        (position[i] * signs[i] * meters_per_unit) + origin_m[i]
        for i in range(3)
    ]
    velocity_m = [
        (velocity[i] * signs[i] * meters_per_unit)
        for i in range(3)
    ]

    # Calculate speed_m_s
    speed_m_s = math.sqrt(sum(v**2 for v in velocity_m))

    # Calculate max_position_error_m
    max_position_error_m = 0.0
    for obs in observation_data:
        frame, tick, position, velocity = obs
        # Calculate the expected position using the analytic model
        t = (tick - origin_tick) * seconds_per_tick
        expected_position = [
            p0[i] + v0[i] * t + 0.5 * g[i] * t**2
            for i in range(3)
        ]
        # Calculate the error between the observed and expected position
        error = [
            position[i] - expected_position[i]
            for i in range(3)
        ]
        error_magnitude = math.sqrt(sum(e**2 for e in error))
        if error_magnitude > max_position_error_m:
            max_position_error_m = error_magnitude

    # Find the peak frame
    peak_frame = None
    peak_height_m = -float('inf')
    for obs in observation_data:
        frame, tick, position, velocity = obs
        height = position[2]
        if height > peak_height_m:
            peak_height_m = height
            peak_frame = frame
        elif height == peak_height_m and frame < peak_frame:
            peak_frame = frame

    # Prepare the report
    report = {
        'source_sha256': source_sha256,
        'frame': query_frame,
        'time_seconds': time_seconds,
        'position_m': position_m,
        'speed_m_s': speed_m_s,
        'max_position_error_m': max_position_error_m,
        'peak_frame': peak_frame,
        'peak_height_m': peak_height_m,
        'missing_frames': missing_frames
    }

    return report


for line in sys.stdin:
    print(json.dumps({"ok": True, "report": review(json.loads(line))}), flush=True)
