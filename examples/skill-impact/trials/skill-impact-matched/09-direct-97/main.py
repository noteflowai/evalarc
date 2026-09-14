"""Implement the recording-review contract described in TASK.md."""

import json
import sys
import math


def review(request):
    # Parse the request
    op = request.get('op')
    query_frame = request.get('query_frame')
    recording = request.get('recording')
    metadata = recording.get('metadata')
    observations = recording.get('observations')
    world_from_sensor = metadata.get('world_from_sensor')
    clock = metadata.get('clock')
    analytic = metadata.get('analytic')
    expected_frames = metadata.get('expected_frames')
    source = recording.get('source')
    digest = source.get('sha256')

    # Convert positions and velocities to world coordinates
    world_positions = []
    world_velocities = []
    for obs in observations:
        frame = obs.get('frame')
        position = obs.get('position')
        velocity = obs.get('velocity')
        # Apply world_from_sensor transformation
        # Apply axis signs and unit scale
        world_position = [
            position[0] * world_from_sensor['signs'][0] * world_from_sensor['meters_per_unit'] + world_from_sensor['origin_m'][0],
            position[1] * world_from_sensor['signs'][1] * world_from_sensor['meters_per_unit'] + world_from_sensor['origin_m'][1],
            position[2] * world_from_sensor['signs'][2] * world_from_sensor['meters_per_unit'] + world_from_sensor['origin_m'][2]
        ]
        world_position = [round(p, 6) for p in world_position]
        world_positions.append({"frame": frame, "position": world_position})
        # Apply the same transformation to velocity
        world_velocity = [
            velocity[0] * world_from_sensor['signs'][0] * world_from_sensor['meters_per_unit'],
            velocity[1] * world_from_sensor['signs'][1] * world_from_sensor['meters_per_unit'],
            velocity[2] * world_from_sensor['signs'][2] * world_from_sensor['meters_per_unit']
        ]
        world_velocity = [round(v, 6) for v in world_velocity]
        world_velocities.append({"frame": frame, "velocity": world_velocity})

    # Convert clock ticks to seconds
    clock_origin_tick = clock.get('origin_tick')
    seconds_per_tick = clock.get('seconds_per_tick')
    clock_seconds = []
    for obs in observations:
        tick = obs.get('tick')
        seconds = (tick - clock_origin_tick) * seconds_per_tick
        clock_seconds.append({"frame": obs.get('frame'), "seconds": seconds})

    # Compute speed from velocity
    speeds = []
    for obs in world_velocities:
        velocity = obs.get('velocity')
        speed = math.sqrt(velocity[0]**2 + velocity[1]**2 + velocity[2]**2)
        speeds.append({"frame": obs.get('frame'), "speed": speed})

    # Find the peak of the trajectory based on world height
    # Apply the tie rule: if multiple frames have the same height, the one with the smallest frame number is chosen
    peak = None
    for obs in world_positions:
        position = obs.get('position')
        height = position[2]
        if peak is None or height > peak["height"]:
            peak = {"frame": obs.get('frame'), "height": height}
        elif height == peak["height"]:
            if obs.get('frame') < peak["frame"]:
                peak = {"frame": obs.get('frame'), "height": height}

    # Check if the peak is followed by a substantial interval
    # If the peak is the last frame, it's acceptable
    if peak is not None:
        peak_frame = peak.get('frame')
        if peak_frame < expected_frames[-1]:
            # Find the next frame after the peak
            next_frame = None
            for obs in world_positions:
                if obs.get('frame') > peak_frame:
                    next_frame = obs.get('frame')
                    break
            if next_frame is not None:
                # Check if the next frame is significantly later
                # For simplicity, we'll assume that a frame difference of 5 is substantial
                if next_frame - peak_frame >= 5:
                    pass  # Peak is followed by a substantial interval
                else:
                    # If not, the peak is not valid
                    peak = None
    
    # Return the requested facts
    return {
        "ok": True,
        "report": {
            "digest": digest,
            "world_positions": world_positions,
            "world_velocities": world_velocities,
            "clock_seconds": clock_seconds,
            "speeds": speeds,
            "peak": peak
        }
    }


for line in sys.stdin:
    print(json.dumps({"ok": True, "report": review(json.loads(line))}), flush=True)
