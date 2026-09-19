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
            print(json.dumps({"ok": false, "error": "Invalid JSON"}))
            continue
        if data.get("op") != "review":
            print(json.dumps({"ok": false, "error": "Invalid operation"}))
            continue
        query_frame = data.get("query_frame")
        recording = data.get("recording")
        if not recording:
            print(json.dumps({"ok": false, "error": "Missing recording"}))
            continue
        source_sha256 = recording.get("source", {}).get("sha256")
        metadata = recording.get("metadata")
        observations = recording.get("observations", [])
        
        if not source_sha256:
            print(json.dumps({"ok": false, "error": "Missing source sha256"}))
            continue
        if not metadata:
            print(json.dumps({"ok": false, "error": "Missing metadata"}))
            continue
        
        expected_frames = metadata.get("expected_frames", [])
        world_from_sensor = metadata.get("world_from_sensor", {})
        clock = metadata.get("clock", {})
        analytic = metadata.get("analytic", {})
        
        axes = world_from_sensor.get("axes", [])
        signs = world_from_sensor.get("signs", [])
        origin_m = world_from_sensor.get("origin_m", [])
        meters_per_unit = world_from_sensor.get("meters_per_unit", 1.0)
        
        origin_tick = clock.get("origin_tick", 0)
        seconds_per_tick = clock.get("seconds_per_tick", 1.0)
        
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
            print(json.dumps({"ok": false, "error": "Query frame not found"}))
            continue
        
        # Calculate time_seconds
        tick = query_obs.get("tick")
        if tick is None:
            print(json.dumps({"ok": false, "error": "Missing tick in query frame"}))
            continue
        time_seconds = (tick - origin_tick) * seconds_per_tick
        
        # Calculate position_m
        position = query_obs.get("position")
        if not position:
            print(json.dumps({"ok": false, "error": "Missing position in query frame"}))
            continue
        
        # Apply world_from_sensor transformation
        position_m = [
            position[axes[0]] * signs[0] * meters_per_unit + origin_m[0],
            position[axes[1]] * signs[1] * meters_per_unit + origin_m[1],
            position[axes[2]] * signs[2] * meters_per_unit + origin_m[2]
        ]
        
        # Calculate speed_m_s
        velocity = query_obs.get("velocity")
        if not velocity:
            print(json.dumps({"ok": false, "error": "Missing velocity in query frame"}))
            continue
        
        # Apply world_from_sensor transformation
        velocity_m_s = [
            velocity[axes[0]] * signs[0] * meters_per_unit,
            velocity[axes[1]] * signs[1] * meters_per_unit,
            velocity[axes[2]] * signs[2] * meters_per_unit
        ]
        
        speed_m_s = math.sqrt(sum(v**2 for v in velocity_m_s))
        
        # Calculate max_position_error_m
        max_position_error = 0.0
        for obs in observations:
            frame = obs.get("frame")
            if frame is not None and frame in expected_frames:
                obs_position = obs.get("position")
                if not obs_position:
                    continue
                
                # Apply world_from_sensor transformation
                obs_position_m = [
                    obs_position[axes[0]] * signs[0] * meters_per_unit + origin_m[0],
                    obs_position[axes[1]] * signs[1] * meters_per_unit + origin_m[1],
                    obs_position[axes[2]] * signs[2] * meters_per_unit + origin_m[2]
                ]
                
                # Calculate expected position using analytic model
                t = (obs.get("tick", 0) - origin_tick) * seconds_per_tick
                expected_position = [
                    position0_m[0] + velocity0_m_s[0] * t + 0.5 * gravity_m_s2[0] * t**2,
                    position0_m[1] + velocity0_m_s[1] * t + 0.5 * gravity_m_s2[1] * t**2,
                    position0_m[2] + velocity0_m_s[2] * t + 0.5 * gravity_m_s2[2] * t**2
                ]
                
                # Calculate error
                error = math.sqrt(sum((obs_position_m[i] - expected_position[i])**2 for i in range(3)))
                if error > max_position_error:
                    max_position_error = error
        
        # Find peak_frame and peak_height_m
        peak_frame = None
        peak_height_m = -math.inf
        for frame in expected_frames:
            if frame in frame_to_observation:
                obs = frame_to_observation[frame][0]
                obs_position = obs.get("position")
                if not obs_position:
                    continue
                
                # Apply world_from_sensor transformation
                obs_position_m = [
                    obs_position[axes[0]] * signs[0] * meters_per_unit + origin_m[0],
                    obs_position[axes[1]] * signs[1] * meters_per_unit + origin_m[1],
                    obs_position[axes[2]] * signs[2] * meters_per_unit + origin_m[2]
                ]
                
                if obs_position_m[2] > peak_height_m:
                    peak_height_m = obs_position_m[2]
                    peak_frame = frame
                elif obs_position_m[2] == peak_height_m:
                    if frame < peak_frame:
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
            "max_position_error_m": max_position_error,
            "peak_frame": peak_frame,
            "peak_height_m": peak_height_m,
            "missing_frames": sorted(missing_frames)
        }
        
        print(json.dumps({"ok": True, "report": report}))
        
    return

if __name__ == "__main__":
    main()
