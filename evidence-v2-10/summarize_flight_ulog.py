#!/usr/bin/env python3
"""Print comparable dynamics, EKF/magnetometer, and landing metrics from a PX4 ULog."""

import argparse
import math
from pathlib import Path

from pyulog import ULog


def dataset(ulog, name):
    return next((entry for entry in ulog.data_list if entry.name == name), None)


def window(data, start_us, end_us):
    timestamps = data.get("timestamp")
    if timestamps is None:
        return []
    return [
        index
        for index, timestamp in enumerate(timestamps)
        if start_us <= timestamp <= end_us
    ]


def nearest_index(data, timestamp_us):
    timestamps = data.get("timestamp")
    if timestamps is None or len(timestamps) == 0:
        return None
    eligible = [index for index, timestamp in enumerate(timestamps) if timestamp <= timestamp_us]
    return eligible[-1] if eligible else 0


def quaternion_yaw(data, index):
    w, x, y, z = (float(data[f"q[{i}]"][index]) for i in range(4))
    return math.degrees(math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))


def quaternion_rpy(data, index):
    w, x, y, z = (float(data[f"q[{i}]"][index]) for i in range(4))
    roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    sin_pitch = 2 * (w * y - z * x)
    pitch = math.copysign(math.pi / 2, sin_pitch) if abs(sin_pitch) >= 1 else math.asin(sin_pitch)
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return tuple(math.degrees(value) for value in (roll, pitch, yaw))


def extrema(data, field, indices):
    values = [float(data[field][index]) for index in indices]
    return [round(min(values), 4), round(max(values), 4)] if values else None


def first_active_time(data, field, indices, base_us):
    active = [index for index in indices if bool(data[field][index])]
    if not active:
        return None
    return round((float(data["timestamp"][active[0]]) - base_us) / 1e6, 3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ulog", type=Path)
    args = parser.parse_args()

    ulog = ULog(str(args.ulog))
    timestamps = [
        float(entry.data["timestamp"][0])
        for entry in ulog.data_list
        if "timestamp" in entry.data and len(entry.data["timestamp"])
    ]
    base_us = min(timestamps)

    status = dataset(ulog, "vehicle_status")
    if status is None:
        raise SystemExit("ULog has no vehicle_status topic")
    status_times = status.data["timestamp"]
    armed = [index for index, value in enumerate(status.data["arming_state"]) if value == 2]
    if not armed:
        raise SystemExit("ULog contains no armed interval")
    arm_index = armed[0]
    arm_us = float(status_times[arm_index])
    disarms = [
        index for index in range(arm_index + 1, len(status_times))
        if status.data["arming_state"][index] == 1
    ]
    disarm_us = float(status_times[disarms[0]]) if disarms else float("inf")
    arm_indices = window(status.data, arm_us, disarm_us)

    estimate = dataset(ulog, "vehicle_attitude") or dataset(ulog, "estimator_attitude")
    yaw_before = None
    if estimate is not None:
        yaw_index = nearest_index(estimate.data, arm_us)
        if yaw_index is not None:
            yaw_before = round(quaternion_yaw(estimate.data, yaw_index), 3)
        attitude_indices = window(estimate.data, arm_us, disarm_us)
        angles = [quaternion_rpy(estimate.data, index) for index in attitude_indices]
        attitude_extrema = {
            axis: [round(min(row[column] for row in angles), 3), round(max(row[column] for row in angles), 3)]
            for column, axis in enumerate(("roll_deg", "pitch_deg", "yaw_deg"))
        } if angles else None
    else:
        attitude_extrema = None

    flags = dataset(ulog, "estimator_status_flags")
    mag_flags = {}
    if flags is not None:
        post_arm = window(flags.data, arm_us, disarm_us)
        for field in ("cs_mag_fault", "cs_mag_3d", "cs_mag_hdg", "cs_mag_aligned_in_flight", "cs_yaw_align", "fs_bad_hdg", "fs_bad_mag_x", "fs_bad_mag_y", "fs_bad_mag_z"):
            if field in flags.data:
                mag_flags[field] = {
                    "ever_true": any(bool(flags.data[field][index]) for index in post_arm),
                    "first_true_s": first_active_time(flags.data, field, post_arm, base_us),
                }

    position = dataset(ulog, "vehicle_local_position")
    position_extrema = None
    if position is not None:
        position_indices = window(position.data, arm_us, disarm_us)
        position_extrema = {
            field: extrema(position.data, field, position_indices)
            for field in ("x", "y", "z")
        }

    outputs = dataset(ulog, "actuator_outputs")
    output_extrema = None
    if outputs is not None:
        output_indices = window(outputs.data, arm_us, disarm_us)
        output_extrema = {
            f"output[{motor}]": extrema(outputs.data, f"output[{motor}]", output_indices)
            for motor in range(4)
        }

    land = dataset(ulog, "vehicle_land_detected")
    landing = None
    if land is not None:
        after_arm = window(land.data, arm_us, disarm_us)
        landing = {
            field: any(bool(land.data[field][index]) for index in after_arm)
            for field in ("ground_contact", "landed", "at_rest")
        }

    print(f"ulog={args.ulog}")
    print(f"duration_s={ulog.last_timestamp / 1e6:.3f} dropout_count={len(ulog.dropouts)}")
    print(f"arm_s={((arm_us - base_us) / 1e6):.3f} disarm_s={((disarm_us - base_us) / 1e6):.3f}")
    print(f"ekf_yaw_deg_at_arm={yaw_before}")
    print(f"mag_flags_after_arm={mag_flags}")
    print(f"attitude_extrema_deg={attitude_extrema}")
    print(f"local_position_extrema_m={position_extrema}")
    print(f"motor_output_extrema={output_extrema}")
    print(f"land_detection_during_armed_interval={landing}")
    print(f"failsafe_values={sorted(set(int(status.data['failsafe'][i]) for i in arm_indices))}")


if __name__ == "__main__":
    main()
