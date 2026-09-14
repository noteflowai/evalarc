import sys
import json
import math

def review_recording(recording):
    source_sha256 = recording['source']['sha256']
    query_frame = recording['query_frame']
    metadata = recording['metadata']
    observations = recording['observations']

    # Extract metadata
    expected_frames = metadata['expected_frames']
    world_from_sensor = metadata['world_from_sensor']
    clock = metadata['clock']
    analytic = metadata['analytic']

    axes = world_from_sensor['axes']
    signs = world_from_sensor['signs']
    origin_m = world_from_sensor['origin_m']
    meters_per_unit = world_from_sensor['meters_per_unit']

    origin_tick = clock['origin_tick']
    seconds_per_tick = clock['seconds_per_tick']

    position0_m = analytic['position0_m']
    velocity0_m_s = analytic['velocity0_m_s']
    gravity_m_s2 = analytic['gravity_m_s2']

    # Process observations
    frame_to_observation = {}
    missing_frames = []
    for obs in observations:
        frame = obs['frame']
        if frame not in expected_frames:
            missing_frames.append(frame)
        else:
            frame_to_observation[frame] = obs

    # Sort missing frames
    missing_frames.sort()

    # Find the queried frame
    query_obs = frame_to_observation.get(query_frame)
    if query_obs is None:
        raise ValueError(f"Query frame {query_frame} not found in observations")

    # Convert query frame's position and velocity to world coordinates
    query_position = query_obs['position']
    query_velocity = query_obs['velocity']
    
    # Convert position
    world_position = [
        signs[axes[0]] * meters_per_unit * query_position[0] + origin_m[0],
        signs[axes[1]] * meters_per_unit * query_position[1] + origin_m[1],
        signs[axes[2]] * meters_per_unit * query_position[2] + origin_m[2]
    ]

    # Convert velocity
    world_velocity = [
        signs[axes[0]] * meters_per_unit * query_velocity[0],
        signs[axes[1]] * meters_per_unit * query_velocity[1],
        signs[axes[2]] * meters_per_unit * query_velocity[2]
    ]

    # Calculate time in seconds for the query frame
    query_tick = query_obs['tick']
    time_seconds = (query_tick - origin_tick) * seconds_per_tick

    # Calculate speed
    speed_m_s = math.sqrt(sum(v**2 for v in world_velocity))

    # Calculate max position error
    max_position_error_m = 0.0
    for frame in expected_frames:
        if frame not in frame_to_observation:
            continue
        obs = frame_to_observation[frame]
        tick = obs['tick']
        
        # Calculate expected position using analytic model
        time = (tick - origin_tick) * seconds_per_tick
        expected_position = [
            position0_m[0] + velocity0_m_s[0] * time + 0.5 * gravity_m_s2[0] * time**2,
            position0_m[1] + velocity0_m_s[1] * time + 0.5 * gravity_m_s2[1] * time**2,
            position0_m[2] + velocity0_m_s[2] * time + 0.5 * gravity_m_s2[2] * time**2
        ]
        
        # Convert observed position to world coordinates
        observed_position = obs['position']
        world_observed_position = [
            signs[axes[0]] * meters_per_unit * observed_position[0] + origin_m[0],
            signs[axes[1]] * meters_per_unit * observed_position[1] + origin_m[1],
            signs[axes[2]] * meters_per_unit * observed_position[2] + origin_m[2]
        ]
        
        # Calculate error
        error = [
            world_observed_position[i] - expected_position[i] for i in range(3)
        ]
        error_magnitude = math.sqrt(sum(e**2 for e in error))
        
        if error_magnitude > max_position_error_m:
            max_position_error_m = error_magnitude

    # Find peak frame
    peak_frame = None
    peak_height_m = -float('inf')
    for frame in expected_frames:
        if frame not in frame_to_observation:
            continue
        obs = frame_to_observation[frame]
        
        # Convert position to world coordinates
        observed_position = obs['position']
        world_observed_position = [
            signs[axes[0]] * meters_per_unit * observed_position[0] + origin_m[0],
            signs[axes[1]] * meters_per_unit * observed_position[1] + origin_m[1],
            signs[axes[2]] * meters_per_unit * observed_position[2] + origin_m[2]
        ]
        
        height = world_observed_position[2]
        
        if height > peak_height_m:
            peak_height_m = height
            peak_frame = frame
        elif height == peak_height_m and frame < peak_frame:
            peak_frame = frame

    # Prepare report
    report = {
        'source_sha256': source_sha256,
        'frame': query_frame,
        'time_seconds': time_seconds,
        'position_m': world_position,
        'speed_m_s': speed_m_s,
        'max_position_error_m': max_position_error_m,
        'peak_frame': peak_frame,
        'peak_height_m': peak_height_m,
        'missing_frames': missing_frames
    }

    return report

# Main function to read from stdin and write to stdout
def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        
        try:
            recording = json.loads(line)
            if recording['op'] != 'review':
                print(json.dumps({'ok': False, 'error': 'Invalid operation'}))
                continue
            
            report = review_recording(recording)
            print(json.dumps({'ok': True, 'report': report}))
        except Exception as e:
            print(json.dumps({'ok': False, 'error': str(e)}))

if __name__ == '__main__':
    main()
