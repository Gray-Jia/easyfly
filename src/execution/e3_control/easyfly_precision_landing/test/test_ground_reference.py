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

"""Independent ground datum regression, never launch simulation or flight."""

import copy
import math

from easyfly_msgs.msg import UAVState
from gazebo_msgs.srv import GetEntityState
from easyfly_precision_landing.simulation_reference import (
    fixture_plane_world_z, ground_sample, height_reference,
)
import pytest


def inputs():
    """Provide explicit stationary disarmed odom/world snapshots."""
    state = UAVState(connected=True, pose_valid=True, attitude_valid=True,
                     velocity_valid=True, position_z=0.14)
    state.header.frame_id = "odom"
    state.header.stamp.sec = 10
    entity = GetEntityState.Response(success=True)
    entity.header.frame_id = "world"
    entity.header.stamp.sec = 10
    entity.state.pose.position.z = 0.1
    return state, entity


def test_reference_is_independent_of_initial_odom_height():
    """An odom origin shift changes the plane, not geometry/quality tolerances."""
    state, entity = inputs()
    row = ground_sample(state, 100.0, entity, 10000000000, 100.0, 100.0, 0.1)
    rows = [{**row, "source_ns": row["source_ns"] + index * 250000000,
             "world_source_ns": row["world_source_ns"] + index * 250000000,
             "steady_s": 100.0 + index * 0.25} for index in range(10)]
    corrected = height_reference(rows, 0.0380925031248085)
    assert corrected["offset_z_m"] == pytest.approx(0.04)
    assert corrected["plane_z_m"] == pytest.approx(0.0780925031248085)
    observed = 0.097005
    assert abs(observed - (0.0380925031248085 - 0.1)) > 0.15
    assert abs(observed - corrected["plane_z_m"]) < 0.15


def test_tag_face_height_includes_tilted_visual_face_offset():
    """The fiducial top faces are one millimeter above its model origin."""
    pose = [0.15, 0.0, 0.038, 0.0, math.radians(8), 0.0]
    assert fixture_plane_world_z(pose, [0.001] * 64) == pytest.approx(
        0.038 + 0.001 * math.cos(math.radians(8)))
    with pytest.raises(ValueError):
        fixture_plane_world_z(pose, [0.001, 0.002])


@pytest.mark.parametrize("shift", [-0.2, 0.0, 0.15, 0.3])
def test_height_gate_is_invariant_under_a_fixed_odom_origin_shift(shift):
    """The measured tag and known plane translate together, without a wider gate."""
    state, entity = inputs()
    entity.state.pose.position.z = 0.054
    state.position_z = 0.14 + shift
    sample = ground_sample(state, 100.0, entity, 10000000000, 100.0, 100.0, 0.055)
    rows = [{**sample, "source_ns": 10000000000 + index * 250000000,
             "world_source_ns": 10000000000 + index * 250000000,
             "steady_s": 100.0 + index * 0.25} for index in range(10)]
    plane = height_reference(rows, 0.03908277119355008)["plane_z_m"]
    measured_center = 0.097005 + shift
    assert abs(measured_center - plane) == pytest.approx(0.02807777119355008)
    assert abs(measured_center - plane) < 0.15


@pytest.mark.parametrize("fault", [
    "armed", "disconnected", "pose_invalid", "velocity_invalid", "moving",
    "world_moving", "world_rotating", "not_ground", "nan", "quaternion", "world_tilt",
    "wrong_odom", "wrong_world", "failed_service", "old_source", "old_receipt",
    "old_request", "unmatched", "zero_clock", "unknown",
])
def test_untrusted_ground_samples_are_rejected(fault):
    """No stale, airborne, moving, unknown or externally armed datum is frozen."""
    state, entity = inputs()
    receipt = began = now = 100.0
    ros_now = 10000000000
    if fault == "armed":
        state.armed = True
    elif fault == "disconnected":
        state.connected = False
    elif fault == "pose_invalid":
        state.pose_valid = False
    elif fault == "velocity_invalid":
        state.velocity_valid = False
    elif fault == "moving":
        state.velocity_z = 0.06
    elif fault == "world_moving":
        entity.state.twist.linear.z = 0.06
    elif fault == "world_rotating":
        entity.state.twist.angular.z = 0.06
    elif fault == "not_ground":
        entity.state.pose.position.z = 0.3
    elif fault == "nan":
        state.position_z = math.nan
    elif fault == "quaternion":
        entity.state.pose.orientation.w = 0.0
    elif fault == "world_tilt":
        entity.state.pose.orientation.x = math.sin(0.1)
        entity.state.pose.orientation.w = math.cos(0.1)
    elif fault == "wrong_odom":
        state.header.frame_id = "map"
    elif fault == "wrong_world":
        entity.header.frame_id = "odom"
    elif fault == "failed_service":
        entity.success = False
    elif fault == "old_source":
        ros_now += 400000000
    elif fault == "old_receipt":
        receipt -= 0.4
    elif fault == "old_request":
        began -= 0.4
    elif fault == "unmatched":
        entity.header.stamp.nanosec = 150000000
    elif fault == "zero_clock":
        ros_now = 0
    else:
        entity = None
    with pytest.raises(ValueError):
        ground_sample(state, receipt, entity, ros_now, now, began, 0.1)


@pytest.mark.parametrize("fault", [
    "short", "duplicate", "rewind", "world_duplicate", "short_duration",
    "offset_drift", "ground_drift", "nan", "large_offset",
])
def test_unstable_or_replayed_reference_cannot_start_precision(fault):
    """Require distinct advancing pairs over a stable bounded ground interval."""
    rows = [{"source_ns": 10000000000 + index * 250000000,
             "world_source_ns": 10000000000 + index * 250000000,
             "steady_s": 100.0 + index * 0.25,
             "offset_z_m": 0.04, "world_z_m": 0.1} for index in range(10)]
    rows = copy.deepcopy(rows)
    if fault == "short":
        rows.pop()
    elif fault == "duplicate":
        rows[-1]["source_ns"] = rows[-2]["source_ns"]
    elif fault == "rewind":
        rows[-1]["source_ns"] = 1
    elif fault == "world_duplicate":
        rows[-1]["world_source_ns"] = rows[-2]["world_source_ns"]
    elif fault == "short_duration":
        for index, row in enumerate(rows):
            row["steady_s"] = 100.0 + index * 0.01
    elif fault == "offset_drift":
        rows[-1]["offset_z_m"] += 0.04
    elif fault == "ground_drift":
        rows[-1]["world_z_m"] += 0.01
    elif fault == "nan":
        rows[-1]["offset_z_m"] = math.nan
    else:
        for row in rows:
            row["offset_z_m"] = 2.0
    with pytest.raises(ValueError):
        height_reference(rows, 0.038)
