"""Implement the recording-review contract described in TASK.md."""

import json
import sys
import math


def review(request):
    # Extract the necessary information from the request
    trace = request.get('trace', [])
    contract = request.get('contract', {})
    facts = request.get('facts', [])

    # Process each fact in the request
    report = {}
    for fact in facts:
        if fact == 'position':
            report['position'] = compute_position(trace, contract)
        elif fact == 'velocity':
            report['velocity'] = compute_velocity(trace, contract)
        elif fact == 'coordinate-frame':
            report['coordinate-frame'] = compute_coordinate_frame(trace, contract)
        elif fact == 'clock':
            report['clock'] = compute_clock(trace, contract)
        elif fact == 'missing-sample':
            report['missing-sample'] = compute_missing_samples(trace, contract)
        else:
            report[fact] = "Unknown fact"

    return report


def compute_position(trace, contract):
    # Convert positions into the same world convention
    positions = []
    for observation in trace:
        position = observation.get('position', [])
        if position:
            # Apply axis signs and unit scale to the position
            converted_position = [p * contract.get('unit_scale', 1) for p in position]
            positions.append(converted_position)
    return positions


def compute_velocity(trace, contract):
    # Compute velocity from positions
    velocities = []
    for i in range(1, len(trace)):
        # Calculate the difference in position between consecutive observations
        position_diff = [trace[i]['position'][j] - trace[i-1]['position'][j] for j in range(len(trace[i]['position']))]
        # Calculate the time difference between consecutive observations
        time_diff = trace[i]['timestamp'] - trace[i-1]['timestamp']
        # Compute velocity
        velocity = [diff / time_diff for diff in position_diff]
        velocities.append(velocity)
    return velocities


def compute_coordinate_frame(trace, contract):
    # Determine the coordinate frame based on the contract
    coordinate_frame = contract.get('coordinate-frame', 'world')
    return coordinate_frame


def compute_clock(trace, contract):
    # Compute clock information based on the contract
    clock_origin = contract.get('clock-origin', 0)
    clock_scale = contract.get('clock-scale', 1)
    clock = []
    for observation in trace:
        # Convert timestamp to clock time
        clock_time = (observation['timestamp'] - clock_origin) * clock_scale
        clock.append(clock_time)
    return clock


def compute_missing_samples(trace, contract):
    # Check for missing samples in the trace
    missing_samples = []
    for i in range(1, len(trace)):
        # Check if the timestamp difference is greater than the expected interval
        expected_interval = contract.get('sample-interval', 1)
        if trace[i]['timestamp'] - trace[i-1]['timestamp'] > expected_interval:
            missing_samples.append(i-1)
    return missing_samples


for line in sys.stdin:
    print(json.dumps({"ok": True, "report": review(json.loads(line))}), flush=True)