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
    time_seconds = (query_frame - clock["origin_tick"]) * clock["seconds_per_tick"]
    
    # Convert position and velocity using world_from_sensor
    position_m = [0.0, 0.0, 0.0]
    velocity_m_s = [0.0, 0.0, 0.0]
    for i in range(3):
        position_m[i] = (world_from_sensor["axes"][i] * world_from_sensor["signs"][i] * 
                        world_from_sensor["meters_per_unit"] * 
                        observations[i]["position"][i] + 
                        world_from_sensor["origin_m"][i])
        velocity_m_s[i] = (world_from_sensor["axes"][i] * world_from_sensor["signs"][i] * 
                          world_from_sensor["meters_per_unit"] * 
                          observations[i]["velocity"][i])
    
    # Calculate speed_m_s
    speed_m_s = (position_m[0]**2 + position_m[1]**2 + position_m[2]**2)**0.5
    
    # Calculate max_position_error_m
    max_position_error_m = 0.0
    for observation in observations:
        if observation["frame"] in expected_frames:
            # Calculate expected position using analytic
            t = (observation["tick"] - clock["origin_tick"]) * clock["seconds_per_tick"]
            expected_position = [
                analytic["position0_m"][0] + analytic["velocity0_m_s"][0] * t + 0.5 * analytic["gravity_m_s2"][0] * t**2,
                analytic["position0_m"][1] + analytic["velocity0_m_s"][1] * t + 0.5 * analytic["gravity_m_s2"][1] * t**2,
                analytic["position0_m"][2] + analytic["velocity0_m_s"][2] * t + 0.5 * analytic["gravity_m_s2"][2] * t**2
            ]
            # Calculate actual position
            actual_position = observation["position"]
            # Calculate error
            error = (actual_position[0] - expected_position[0])**2 + (actual_position[1] - expected_position[1])**2 + (actual_position[2] - expected_position[2])**2
            error = error**0.5
            if error > max_position_error_m:
                max_position_error_m = error
    
    # Find peak_frame and peak_height_m
    peak_frame = None
    peak_height_m = -float('inf')
    for frame in expected_frames:
        for observation in observations:
            if observation["frame"] == frame:
                # Calculate world z position
                z_position = (world_from_sensor["axes"][2] * world_from_sensor["signs"][2] * 
                              world_from_sensor["meters_per_unit"] * 
                              observation["position"][2] + 
                              world_from_sensor["origin_m"][2])
                if z_position > peak_height_m:
                    peak_height_m = z_position
                    peak_frame = frame
                elif z_position == peak_height_m and frame < peak_frame:
                    peak_frame = frame
                    peak_height_m = z_position
    
    # Find missing_frames
    missing_frames = []
    for frame in expected_frames:
        found = False
        for observation in observations:
            if observation["frame"] == frame:
                found = True
                break
        if not found:
            missing_frames.append(frame)
    
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
