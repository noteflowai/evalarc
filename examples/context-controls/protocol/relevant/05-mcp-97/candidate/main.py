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

def calculate_position_analytic(t, analytic):
    position0 = analytic['position0_m']
    velocity0 = analytic['velocity0_m_s']
    gravity = analytic['gravity_m_s2']
    return [
        position0[0] + velocity0[0] * t + 0.5 * gravity[0] * t * t,
        position0[1] + velocity0[1] * t + 0.5 * gravity[1] * t * t,
        position0[2] + velocity0[2] * t + 0.5 * gravity[2] * t * t
    ]

def calculate_speed(velocity):
    return math.sqrt(sum(v**2 for v in velocity))

def find_peak_frame(observations):
    max_z = -float('inf')
    peak_frame = None
    for obs in observations:
        z = obs['position'][2]
        if z > max_z or (z == max_z and obs['frame'] < peak_frame):
            max_z = z
            peak_frame = obs['frame']
    return peak_frame, max_z

def main():
    for line in sys.stdin:
        request = json.loads(line)
        recording = request['recording']
        source_sha256 = recording['source']['sha256']
        query_frame = request['query_frame']
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
        queried_obs = None
        for obs in observations:
            if obs['frame'] == query_frame:
                queried_obs = obs
                break
        
        # Convert queried frame's position and velocity
        queried_position = convert_position(queried_obs['position'], axes, signs, origin_m, meters_per_unit)
        queried_velocity = convert_velocity(queried_obs['velocity'], axes, signs, meters_per_unit)
        
        # Calculate time for queried frame
        queried_time = calculate_time(queried_obs['tick'], clock)
        
        # Calculate speed
        speed = calculate_speed(queried_velocity)
        
        # Calculate max position error
        max_position_error = 0.0
        for obs in observations:
            if obs['frame'] == query_frame:
                continue
            t = calculate_time(obs['tick'], clock)
            analytic_position = calculate_position_analytic(t, analytic)
            error = [
                obs['position'][axes[0]] * signs[0] * meters_per_unit + origin_m[0] - analytic_position[0],
                obs['position'][axes[1]] * signs[1] * meters_per_unit + origin_m[1] - analytic_position[1],
                obs['position'][axes[2]] * signs[2] * meters_per_unit + origin_m[2] - analytic_position[2]
            ]
            error_magnitude = math.sqrt(sum(e**2 for e in error))
            if error_magnitude > max_position_error:
                max_position_error = error_magnitude
        
        # Find peak frame
        peak_frame, peak_height = find_peak_frame(observations)
        
        # Find missing frames
        missing_frames = [f for f in expected_frames if not any(obs['frame'] == f for obs in observations)]
        missing_frames.sort()
        
        # Prepare report
        report = {
            'source_sha256': source_sha256,
            'frame': query_frame,
            'time_seconds': queried_time,
            'position_m': queried_position,
            'speed_m_s': speed,
            'max_position_error_m': max_position_error,
            'peak_frame': peak_frame,
            'peak_height_m': peak_height,
            'missing_frames': missing_frames
        }
        
        # Output the report
        print(json.dumps({'ok': True, 'report': report}))
        sys.stdout.flush()

if __name__ == '__main__':
    main()
