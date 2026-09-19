import sys
import json
import math

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            print(json.dumps({"ok": False, "report": {}}))
            continue
        if data.get("op") != "review":
            print(json.dumps({"ok": False, "report": {}}))
            continue
        query_frame = data.get("query_frame")
        recording = data.get("recording")
        source_sha256 = recording.get("source", {}).get("sha256")
        metadata = recording.get("metadata")
        expected_frames = metadata.get("expected_frames")
        world_from_sensor = metadata.get("world_from_sensor")
        clock = metadata.get("clock")
        analytic = metadata.get("analytic")
        observations = recording.get("observations")
        
        # Process observations
        observations_by_frame = {}
        for obs in observations:
            frame = obs.get("frame")
            if frame is not None:
                observations_by_frame[frame] = obs
        
        # Find query frame
        query_obs = observations_by_frame.get(query_frame)
        if query_obs is None:
            print(json.dumps({"ok": False, "report": {}}))
            continue
        
        # Calculate time_seconds
        tick = query_obs.get("tick")
        origin_tick = clock.get("origin_tick")
        seconds_per_tick = clock.get("seconds_per_tick")
        time_seconds = (tick - origin_tick) * seconds_per_tick
        
        # Calculate position_m
        position = query_obs.get("position")
        axes = world_from_sensor.get("axes")
        signs = world_from_sensor.get("signs")
        origin_m = world_from_sensor.get("origin_m")
        meters_per_unit = world_from_sensor.get("meters_per_unit")
        
        position_m = [
            (position[axes[0]] * signs[0] * meters_per_unit) + origin_m[0],
            (position[axes[1]] * signs[1] * meters_per_unit) + origin_m[1],
            (position[axes[2]] * signs[2] * meters_per_unit) + origin_m[2]
        ]
        
        # Calculate speed_m_s
        velocity = query_obs.get("velocity")
        speed_m_s = math.sqrt(
            (velocity[axes[0]] * signs[0] * meters_per_unit) ** 2 +
            (velocity[axes[1]] * signs[1] * meters_per_unit) ** 2 +
            (velocity[axes[2]] * signs[2] * meters_per_unit) ** 2
        )
        
        # Calculate max_position_error_m
        p0_m = analytic.get("position0_m")
        v0_m_s = analytic.get("velocity0_m_s")
        g_m_s2 = analytic.get("gravity_m_s2")
        
        max_error = 0.0
        for frame in observations_by_frame:
            obs = observations_by_frame[frame]
            t = (obs.get("tick") - origin_tick) * seconds_per_tick
            expected_position = [
                p0_m[0] + v0_m_s[0] * t + 0.5 * g_m_s2[0] * t * t,
                p0_m[1] + v0_m_s[1] * t + 0.5 * g_m_s2[1] * t * t,
                p0_m[2] + v0_m_s[2] * t + 0.5 * g_m_s2[2] * t * t
            ]
            actual_position = obs.get("position")
            error = math.sqrt(
                (actual_position[axes[0]] * signs[0] * meters_per_unit - expected_position[0]) ** 2 +
                (actual_position[axes[1]] * signs[1] * meters_per_unit - expected_position[1]) ** 2 +
                (actual_position[axes[2]] * signs[2] * meters_per_unit - expected_position[2]) ** 2
            )
            if error > max_error:
                max_error = error
        
        # Find peak_frame and peak_height_m
        peak_frame = None
        peak_height_m = -float('inf')
        for frame in observations_by_frame:
            obs = observations_by_frame[frame]
            z = obs.get("position")[axes[2]] * signs[2] * meters_per_unit + origin_m[2]
            if z > peak_height_m:
                peak_height_m = z
                peak_frame = frame
            elif z == peak_height_m and frame < peak_frame:
                peak_frame = frame
        
        # Find missing_frames
        missing_frames = []
        for frame in expected_frames:
            if frame not in observations_by_frame:
                missing_frames.append(frame)
        missing_frames.sort()
        
        # Prepare report
        report = {
            "source_sha256": source_sha256,
            "frame": query_frame,
            "time_seconds": time_seconds,
            "position_m": position_m,
            "speed_m_s": speed_m_s,
            "max_position_error_m": max_error,
            "peak_frame": peak_frame,
            "peak_height_m": peak_height_m,
            "missing_frames": missing_frames
        }
        
        print(json.dumps({"ok": True, "report": report}))
        
    return

if __name__ == "__main__":
    main()
