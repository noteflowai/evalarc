import sys
import json
import math

def convert_position(position, axes, signs, origin_m, meters_per_unit):
    converted = [
        position[axes[0]] * signs[0] * meters_per_unit + origin_m[0],
        position[axes[1]] * signs[1] * meters_per_unit + origin_m[1],
        position[axes[2]] * signs[2] * meters_per_unit + origin_m[2]
    ]
    return converted

def convert_velocity(velocity, axes, signs, meters_per_unit):
    converted = [
        velocity[axes[0]] * signs[0] * meters_per_unit,
        velocity[axes[1]] * signs[1] * meters_per_unit,
        velocity[axes[2]] * signs[2] * meters_per_unit
    ]
    return converted

def calculate_time(tick, clock):
    return (tick - clock['origin_tick']) * clock['seconds_per_tick']

def calculate_position(t, analytic):
    return [
        analytic['position0_m'][0] + analytic['velocity0_m_s'][0] * t + 0.5 * analytic['gravity_m_s2'][0] * t**2,
        analytic['position0_m'][1] + analytic['velocity0_m_s'][1] * t + 0.5 * analytic['gravity_m_s2'][1] * t**2,
        analytic['position0_m'][2] + analytic['velocity0_m_s'][2] * t + 0.5 * analytic['gravity_m_s2'][2] * t**2
    ]

def calculate_speed(velocity):
    return math.sqrt(sum(v**2 for v in velocity))

def main():
    for line in sys.stdin:
        try:
            data = json.loads(line)
            if data['op'] != 'review':
                continue
            query_frame = data['query_frame']
            recording = data['recording']
            source_sha256 = recording['source']['sha256']
            metadata = recording['metadata']
            expected_frames = metadata['expected_frames']
            world_from_sensor = metadata['world_from_sensor']
            axes = world_from_sensor['axes']
            signs = world_from_sensor['signs']
            origin_m = world_from_sensor['origin_m']
            meters_per_unit = world_from_sensor['meters_per_unit']
            clock = metadata['clock']
            analytic = metadata['analytic']
            observations = recording['observations']
            
            # Find the queried frame
            queried_observation = None
            for obs in observations:
                if obs['frame'] == query_frame:
                    queried_observation = obs
                    break
            if not queried_observation:
                print(json.dumps({"ok": False, "report": {}}))
                continue
            
            # Convert queried observation to world coordinates
            queried_position = convert_position(queried_observation['position'], axes, signs, origin_m, meters_per_unit)
            queried_velocity = convert_velocity(queried_observation['velocity'], axes, signs, meters_per_unit)
            
            # Calculate time for queried frame
            queried_time = calculate_time(queried_observation['tick'], clock)
            
            # Calculate position using analytic model
            analytic_position = calculate_position(queried_time, analytic)
            
            # Calculate speed
            speed = calculate_speed(queried_velocity)
            
            # Calculate max position error
            max_position_error = 0.0
            for obs in observations:
                if obs['frame'] in expected_frames:
                    obs_position = convert_position(obs['position'], axes, signs, origin_m, meters_per_unit)
                    error = [
                        obs_position[0] - analytic_position[0],
                        obs_position[1] - analytic_position[1],
                        obs_position[2] - analytic_position[2]
                    ]
                    error_magnitude = math.sqrt(sum(e**2 for e in error))
                    if error_magnitude > max_position_error:
                        max_position_error = error_magnitude
            
            # Find peak frame
            peak_frame = None
            peak_height = -float('inf')
            for obs in observations:
                if obs['frame'] in expected_frames:
                    obs_position = convert_position(obs['position'], axes, signs, origin_m, meters_per_unit)
                    if obs_position[2] > peak_height:
                        peak_height = obs_position[2]
                        peak_frame = obs['frame']
                    elif obs_position[2] == peak_height and obs['frame'] < peak_frame:
                        peak_frame = obs['frame']
            
            # Find missing frames
            missing_frames = [f for f in expected_frames if not any(obs['frame'] == f for obs in observations)]
            missing_frames.sort()
            
            # Prepare report
            report = {
                "source_sha256": source_sha256,
                "frame": query_frame,
                "time_seconds": queried_time,
                "position_m": queried_position,
                "speed_m_s": speed,
                "max_position_error_m": max_position_error,
                "peak_frame": peak_frame,
                "peak_height_m": peak_height,
                "missing_frames": missing_frames
            }
            
            print(json.dumps({"ok": True, "report": report}))
        except Exception as e:
            print(json.dumps({"ok": False, "report": {}}))

if __name__ == '__main__':
    main()
