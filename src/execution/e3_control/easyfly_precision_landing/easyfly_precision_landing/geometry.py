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

"""Rigid geometry only; optical depth is never used as vertical clearance."""

import math


def finite(values):
    """Check all coordinates without accepting infinities or NaN."""
    return all(math.isfinite(value) for value in values)


def rotation(quaternion):
    """Return row-major rotation for an explicitly unit xyzw quaternion."""
    if len(quaternion) != 4 or not finite(quaternion):
        raise ValueError("invalid quaternion")
    x, y, z, w = quaternion
    if abs(sum(value * value for value in quaternion) - 1.0) > 1e-4:
        raise ValueError("quaternion must be unit length")
    return (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    )


def attitude(roll, pitch, yaw):
    """Return the FLU-to-ENU matrix from the trusted vehicle attitude."""
    if not finite((roll, pitch, yaw)):
        raise ValueError("invalid attitude")
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    return (
        (cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr),
        (sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr),
        (-sp, cp * sr, cp * cr),
    )


def apply(matrix, vector):
    """Rotate one three-vector."""
    return tuple(sum(row[i] * vector[i] for i in range(3)) for row in matrix)


def transform(
    point,
    tag_quaternion,
    camera_translation,
    camera_quaternion,
    vehicle_position,
    vehicle_rpy,
):
    """
    Convert camera-observed tag center and normal to odom.

    The extrinsic is T_base_link_camera_optical: camera origin and orientation
    expressed in FLU base_link. The observation is T_camera_optical_tag.
    """
    vectors = (point, camera_translation, vehicle_position, vehicle_rpy)
    if any(len(vector) != 3 or not finite(vector) for vector in vectors):
        raise ValueError("invalid coordinates")
    if point[2] <= 0:
        raise ValueError("tag behind camera")
    camera = rotation(camera_quaternion)
    world = attitude(*vehicle_rpy)
    offset = apply(camera, point)
    body_point = tuple(offset[i] + camera_translation[i] for i in range(3))
    world_offset = apply(world, body_point)
    center = tuple(world_offset[i] + vehicle_position[i] for i in range(3))
    tag = rotation(tag_quaternion)
    normal = apply(world, apply(camera, apply(tag, (0.0, 0.0, 1.0))))
    return center, normal
