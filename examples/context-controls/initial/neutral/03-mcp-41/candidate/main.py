import sys
import json
import math
from collections import defaultdict

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            print(json.dumps({"ok": False, "error": "Invalid JSON"}))
            continue
        if data.get("op") != "review":
            print(json.dumps({"ok": False, "error": "Invalid operation"}))
            continue
        query_frame = data.get("query_frame")
        recording = data.get("recording")
        if not recording:
            print(json.dumps({"ok": False, "error": "Missing recording"}))
            continue
        source_sha256 = recording.get("source", {}).get("sha256")
        metadata = recording.get("metadata")
        observations = recording.get("observations", [])
        
        # Extract metadata
        expected_frames = metadata.get("expected_frames", [])
        world_from_sensor = metadata.get("world_from_sensor", {})
        clock = metadata.get("clock", {})
        analytic = metadata.get("analytic", {})
        
        # Extract world_from_sensor parameters
        axes = world_from_sensor.get("axes", [])
        signs = world_from_sensor.get("signs", [])
        origin_m = world_from_sensor.get("origin_m", [])
        meters_per_unit = world_from_sensor.get("meters_per_unit", 1.0)
        
        # Extract clock parameters
        origin_tick = clock.get("origin_tick", 0)
        seconds_per_tick = clock.get("seconds_per_tick", 1.0)
        
        # Extract analytic parameters
        position0_m = analytic.get("position0_m", [])
        velocity0_m_s = analytic.get("velocity0_m_s", [])
        gravity_m_s2 = analytic.get("gravity_m_s2", [])
        
        # Process observations
        frame_to_observation = defaultdict(list)
        for obs in observations:
            frame = obs.get("frame")
            if frame is not None:
                frame_to_observation[frame].append(obs)
        
        # Find the queried frame
        query_obs = None
        for obs in frame_to_observation.get(query_frame, []):
            if obs.get("frame") == query_frame:
                query_obs = obs
                break
        
        if not query_obs:
            print(json.dumps({"ok": False, "error": "Query frame not found"}))
            continue
        
        # Calculate time_seconds
        tick = query_obs.get("tick")
        if tick is not None:
            time_seconds = (tick - origin_tick) * seconds_per_tick
        else:
            time_seconds = 0.0
        
        # Calculate position_m
        position_m = [0.0, 0.0, 0.0]
        for i in range(3):
            sensor_component = query_obs.get("position")[i]
            position_m[i] = (sensor_component * signs[i] * meters_per_unit) + origin_m[i]
        
        # Calculate speed_m_s
        velocity_m_s = [0.0, 0.0, 0.0]
        for i in range(3):
            sensor_component = query_obs.get("velocity")[i]
            velocity_m_s[i] = sensor_component * signs[i] * meters_per_unit
        
        speed_m_s = math.sqrt(sum(v**2 for v in velocity_m_s))
        
        # Calculate max_position_error_m
        max_position_error_m = 0.0
        for obs in observations:
            frame = obs.get("frame")
            if frame is not None and frame in frame_to_observation:
                obs_position = obs.get("position")
                obs_velocity = obs.get("velocity")
                
                # Calculate expected position using analytic model
                t = (obs.get("tick") - origin_tick) * seconds_per_tick
                expected_position = [
                    position0_m[0] + velocity0_m_s[0] * t + 0.5 * gravity_m_s2[0] * t**2,
                    position0_m[1] + velocity0_m_s[1] * t + 0.5 * gravity_m_s2[1] * t**2,
                    position0_m[2] + velocity0_m_s[2] * t + 0.5 * gravity_m_s2[2] * t**2
                ]
                
                # Calculate actual position
                actual_position = [0.0, 0.0, 0.0]
                for i in range(3):
                    sensor_component = obs_position[i]
                    actual_position[i] = (sensor_component * signs[i] * meters_per_unit) + origin_m[i]
                
                # Calculate position error
                error = math.sqrt(sum((actual_position[i] - expected_position[i])**2 for i in range(3)))
                
                if error > max_position_error_m:
                    max_position_error_m = error
        
        # Find peak_frame and peak_height_m
        peak_frame = None
        peak_height_m = -float('inf')
        for frame in expected_frames:
            if frame in frame_to_observation:
                obs = frame_to_observation[frame][0]
                obs_position = obs.get("position")
                
                # Calculate actual position
                actual_position = [0.0, 0.0, 0.0]
                for i in range(3):
                    sensor_component = obs_position[i]
                    actual_position[i] = (sensor_component * signs[i] * meters_per_unit) + origin_m[i]
                
                if actual_position[2] > peak_height_m:
                    peak_height_m = actual_position[2]
                    peak_frame = frame
                elif actual_position[2] == peak_height_m and frame < peak_frame:
                    peak_frame = frame
        
        # Find missing_frames
        missing_frames = []
        for frame in expected_frames:
            if frame not in frame_to_observation:
                missing_frames.append(frame)
        
        # Prepare report
        report = {
            "source_sha256": source_sha256,
            "frame": query_frame,
            "time_seconds": time_seconds,
            "position_m": position_m,
            "speed_m_s": speed_m_s,
            "max_position_error_m": max_position_error_m,
            "peak_frame": peak_frame,
            "peak_height_m": peak_height_m,
            "missing_frames": sorted(missing_frames)
        }
        
        print(json.dumps({"ok": True, "report": report}))
    
if __name__ == "__main__":
    main()
