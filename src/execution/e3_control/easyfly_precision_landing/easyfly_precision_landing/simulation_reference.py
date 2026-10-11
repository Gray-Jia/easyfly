# Copyright 2026 EasyFly Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Simulation-only ground datum, independent of the landing detector output."""

import math
import statistics

from easyfly_precision_landing.geometry import finite, rotation


def source_ns(header):
    """Reject malformed timestamps without using a system-wall freshness clock."""
    if header.stamp.sec < 0 or not 0 <= header.stamp.nanosec < 1000000000:
        raise ValueError("malformed reference timestamp")
    return header.stamp.sec * 1000000000 + header.stamp.nanosec


def fixture_plane_world_z(board_pose, cell_top_heights):
    """Locate the center of the static tag's top faces, not its model origin."""
    if (len(board_pose) != 6 or not cell_top_heights
            or not finite(list(board_pose) + list(cell_top_heights))
            or max(cell_top_heights) - min(cell_top_heights) > 1e-9):
        raise ValueError("tag faces must share one finite fixture plane")
    return board_pose[2] + cell_top_heights[0] * math.cos(board_pose[3]) * math.cos(board_pose[4])


def ground_sample(state, receipt, entity, ros_now, steady_now, request_started, expected_ground_z):
    """Pair fresh disarmed stationary odom with stamped world base-link truth."""
    if state is None or entity is None:
        raise ValueError("unknown ground reference state")
    source, world_source = source_ns(state.header), source_ns(entity.header)
    if (state.header.frame_id != "odom" or not state.connected or state.armed
            or not state.pose_valid or not state.attitude_valid or not state.velocity_valid
            or not entity.success or entity.header.frame_id != "world"):
        raise ValueError("untrusted ground reference state")
    p, q, twist = entity.state.pose.position, entity.state.pose.orientation, entity.state.twist
    values = (state.position_x, state.position_y, state.position_z,
              state.roll, state.pitch, state.yaw, state.velocity_x, state.velocity_y,
              state.velocity_z, p.x, p.y, p.z, twist.linear.x, twist.linear.y, twist.linear.z,
              twist.angular.x, twist.angular.y, twist.angular.z)
    if not finite(values):
        raise ValueError("nonfinite ground reference")
    world_rotation = rotation((q.x, q.y, q.z, q.w))
    if not math.isfinite(expected_ground_z):
        raise ValueError("unknown fixture ground geometry")
    if (ros_now <= 0 or min(source, world_source) <= 0
            or not -0.2 <= (ros_now - source) * 1e-9 <= 0.3
            or not -0.2 <= (ros_now - world_source) * 1e-9 <= 0.3
            or abs(source - world_source) * 1e-9 > 0.1
            or not 0 <= steady_now - receipt <= 0.3
            or not 0 <= steady_now - request_started <= 0.3):
        raise ValueError("stale or unmatched ground reference")
    speeds = ((state.velocity_x, state.velocity_y, state.velocity_z),
              (twist.linear.x, twist.linear.y, twist.linear.z),
              (twist.angular.x, twist.angular.y, twist.angular.z))
    if (any(math.sqrt(sum(v * v for v in group)) > 0.05 for group in speeds)
            or max(abs(state.roll), abs(state.pitch)) > 0.1
            or world_rotation[2][2] < math.cos(0.1)
            or abs(p.z - expected_ground_z) > 0.02):
        raise ValueError("fixture not stationary on the expected ground")
    return {"source_ns": source, "world_source_ns": world_source, "steady_s": steady_now,
            "state_receipt_steady_s": receipt, "request_started_steady_s": request_started,
            "odom_z_m": state.position_z, "world_z_m": p.z,
            "expected_ground_world_z_m": expected_ground_z,
            "offset_z_m": state.position_z - p.z, "source_gap_s": abs(source - world_source)
            * 1e-9}


def height_reference(samples, board_world_z):
    """Freeze a stable datum before flight; never infer it from tag observations."""
    if len(samples) < 10 or not math.isfinite(board_world_z):
        raise ValueError("insufficient ground reference")
    sources = [item["source_ns"] for item in samples]
    world_sources = [item["world_source_ns"] for item in samples]
    times = [item["steady_s"] for item in samples]
    offsets = [item["offset_z_m"] for item in samples]
    heights = [item["world_z_m"] for item in samples]
    if (not finite(times + offsets + heights)
            or any(b <= a for a, b in zip(sources, sources[1:]))
            or any(b <= a for a, b in zip(world_sources, world_sources[1:]))
            or any(b <= a for a, b in zip(times, times[1:]))
            or times[-1] - times[0] < 1.8
            or max(offsets) - min(offsets) > 0.03
            or max(heights) - min(heights) > 0.005
            or max(abs(value) for value in offsets) > 1.0):
        raise ValueError("unstable or ambiguous ground reference")
    offset = statistics.median(offsets)
    return {"offset_z_m": offset, "plane_z_m": board_world_z + offset,
            "board_world_z_m": board_world_z, "offset_span_m": max(offsets) - min(offsets),
            "samples": samples,
            "provenance": "disarmed stationary UAVState paired with Gazebo base_link world pose"}
