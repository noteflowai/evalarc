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
    
    # Extract source information
    source_sha256 = recording["source"]["sha256"]
    
    # Convert clock to time_seconds
    time_seconds = (request["query_frame"] - clock["origin_tick"]) * clock["seconds_per_tick"]
    
    # Find the observation for the query frame
    query_observation = None
    for obs in observations:
        if obs["frame"] == query_frame:
            query_observation = obs
            break
    
    # Convert position and velocity to world coordinates
    position_m = [0.0, 0.0, 0.0]
    velocity_m_s = [0.0, 0.0, 0.0]
    
    for i in range(3):
        position_m[i] = (world_from_sensor["axes"][i] * query_observation["position"][i] * world_from_sensor["meters_per_unit"])
        position_m[i] += world_from_sensor["origin_m"][i] * world_from_sensor["meters_per_unit"]
        
        velocity_m_s[i] = (world_from_sensor["axes"][i] * query_observation["velocity"][i] * world_from_sensor["meters_per_unit"])
    
    # Calculate speed_m_s
    speed_m_s = (position_m[0]**2 + position_m[1]**2 + position_m[2]**2)**0.5
    
    # Calculate max_position_error_m
    max_position_error_m = 0.0
    
    for obs in observations:
        frame = obs["frame"]
        tick = obs["tick"]
        position = obs["position"]
        velocity = obs["velocity"]
        
        # Convert position and velocity to world coordinates
        obs_position_m = [0.0, 0.0, 0.0]
        obs_velocity_m_s = [0.0, 0.0, 0.0]
        
        for i in range(3):
            obs_position_m[i] = (world_from_sensor["axes"][i] * position[i] * world_from_sensor["meters_per_unit"])
            obs_position_m[i] += world_from_sensor["origin_m"][i] * world_from_sensor["meters_per_unit"]
            
            obs_velocity_m_s[i] = (world_from_sensor["axes"][i] * velocity[i] * world_from_sensor["meters_per_unit"])
        
        # Calculate the expected position using the analytic model
        expected_position_m = [0.0, 0.0, 0.0]
        expected_position_m[0] = analytic["position0_m"][0] + analytic["velocity0_m_s"][0] * (tick - clock["origin_tick"]) * clock["seconds_per_tick"] + 0.5 * analytic["gravity_m_s2"][0] * ((tick - clock["origin_tick"]) * clock["seconds_per_tick"])**2
        expected_position_m[1] = analytic["position0_m"][1] + analytic["velocity0_m_s"][1] * (tick - clock["origin_tick"]) * clock["seconds_per_tick"] + 0.5 * analytic["gravity_m_s2"][1] * ((tick - clock["origin_tick"]) * clock["seconds_per_tick"])**2
        expected_position_m[2] = analytic["position0_m"][2] + analytic["velocity0_m_s"][2] * (tick - clock["origin_tick"]) * clock["seconds_per_tick"] + 0.5 * analytic["gravity_m_s2"][2] * ((tick - clock["origin_tick"]) * clock["seconds_per_tick"])**2
        
        # Calculate the position error
        error = (obs_position_m[0] - expected_position_m[0])**2 + (obs_position_m[1] - expected_position_m[1])**2 + (obs_position_m[2] - expected_position_m[2])**2
        error = error**0.5
        
        # Update max_position_error_m
        if error > max_position_error_m:
            max_position_error_m = error
    
    # Find peak_frame and peak_height_m
    peak_frame = None
    peak_height_m = -float('inf')
    
    for obs in observations:
        frame = obs["frame"]
        tick = obs["tick"]
        position = obs["position"]
        
        # Convert position to world coordinates
        obs_position_m = [0.0, 0.0, 0.0]
        
        for i in range(3):
            obs_position_m[i] = (world_from_sensor["axes"][i] * position[i] * world_from_sensor["meters_per_unit"])
            obs_position_m[i] += world_from_sensor["origin_m"][i] * world_from_sensor["meters_per_unit"]
        
        # Check if this frame is the peak
        if obs_position_m[2] > peak_height_m:
            peak_height_m = obs_position_m[2]
            peak_frame = frame
        elif obs_position_m[2] == peak_height_m and frame < peak_frame:
            peak_frame = frame
    
    # Find missing_frames
    missing_frames = []
    
    for frame in expected_frames:
        found = False
        
        for obs in observations:
            if obs["frame"] == frame:
                found = True
                break
        
        if not found:
            missing_frames.append(frame)
    
    # Sort missing_frames
    missing_frames.sort()
    
    # Return the report
    return {
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


for line in sys.stdin:
    print(json.dumps({"ok": True, "report": review(json.loads(line))}), flush=True)
