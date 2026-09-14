import json
import sys


def review(request):
    # Extract the query frame
    query_frame = request["query_frame"]
    recording = request["recording"]
    
    # Extract metadata
    metadata = recording["metadata"]
    expected_frames = metadata["expected_frames"]
    world_from_sensor = metadata["world_from_sensor"]
    clock = metadata["clock"]
    analytic = metadata["analytic"]
    observations = recording["observations"]
    
    # Extract world_from_sensor details
    axes = world_from_sensor["axes"]
    signs = world_from_sensor["signs"]
    origin_m = world_from_sensor["origin_m"]
    meters_per_unit = world_from_sensor["meters_per_unit"]
    
    # Extract clock details
    origin_tick = clock["origin_tick"]
    seconds_per_tick = clock["seconds_per_tick"]
    
    # Extract analytic details
    position0_m = analytic["position0_m"]
    velocity0_m_s = analytic["velocity0_m_s"]
    gravity_m_s2 = analytic["gravity_m_s2"]
    
    # Extract source details
    source_sha256 = recording["source"]["sha256"]
    
    # Find the queried frame
    queried_frame_observation = None
    for observation in observations:
        if observation["frame"] == query_frame:
            queried_frame_observation = observation
            break
    
    # Calculate time_seconds for the queried frame
    queried_frame_tick = queried_frame_observation["tick"]
    time_seconds = (queried_frame_tick - origin_tick) * seconds_per_tick
    
    # Calculate position_m for the queried frame
    queried_position = queried_frame_observation["position"]
    position_m = [
        (queried_position[i] * signs[axes[i]] * meters_per_unit) + origin_m[i]
        for i in range(3)
    ]
    
    # Calculate speed_m_s for the queried frame
    queried_velocity = queried_frame_observation["velocity"]
    speed_m_s = sum(velocity ** 2 for velocity in queried_velocity) ** 0.5
    
    # Calculate max_position_error_m
    max_position_error_m = 0.0
    for observation in observations:
        frame = observation["frame"]
        tick = observation["tick"]
        position = observation["position"]
        
        # Calculate expected position using analytic model
        time = (tick - origin_tick) * seconds_per_tick
        expected_position = [
            position0_m[i] + velocity0_m_s[i] * time + 0.5 * gravity_m_s2[i] * time ** 2
            for i in range(3)
        ]
        
        # Calculate actual position
        actual_position = [
            (position[i] * signs[axes[i]] * meters_per_unit) + origin_m[i]
            for i in range(3)
        ]
        
        # Calculate position error
        error = sum((actual_position[i] - expected_position[i]) ** 2 for i in range(3)) ** 0.5
        
        # Update max_position_error_m
        if error > max_position_error_m:
            max_position_error_m = error
    
    # Find peak_frame and peak_height_m
    peak_frame = None
    peak_height_m = -float('inf')
    for observation in observations:
        frame = observation["frame"]
        position = observation["position"]
        
        # Calculate world position
        actual_position = [
            (position[i] * signs[axes[i]] * meters_per_unit) + origin_m[i]
            for i in range(3)
        ]
        
        # Check if this frame has the highest z position
        if actual_position[2] > peak_height_m:
            peak_height_m = actual_position[2]
            peak_frame = frame
        elif actual_position[2] == peak_height_m and frame < peak_frame:
            peak_frame = frame
    
    # Find missing_frames
    missing_frames = [frame for frame in expected_frames if not any(observation["frame"] == frame for observation in observations)]
    
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
