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

"""Known rigid geometry, including tilted cameras and invalid inputs."""

import math

from easyfly_precision_landing.geometry import rotation, transform
import pytest


def test_down_camera_translation_and_vehicle_yaw():
    """Account for the camera lever arm and vehicle rotation."""
    root = math.sqrt(0.5)
    center, normal = transform(
        (0.2, -0.1, 1.0),
        (0.0, 0.0, 0.0, 1.0),
        (0.05, 0.0, -0.1),
        (root, -root, 0.0, 0.0),
        (2.0, 3.0, 1.1),
        (0.0, 0.0, math.pi / 2),
    )
    assert center == pytest.approx((2.2, 3.15, 0.0))
    assert normal == pytest.approx((0.0, 0.0, -1.0))


def test_optical_depth_is_not_vertical_height():
    """A tilted ray has different optical depth and vertical separation."""
    angle = math.pi / 6
    center, _ = transform(
        (0.0, 0.0, 2.0),
        (0.0, 0.0, 0.0, 1.0),
        (0.0, 0.0, 0.0),
        (math.sin(angle / 2), 0.0, 0.0, math.cos(angle / 2)),
        (0.0, 0.0, 3.0),
        (0.0, 0.0, 0.0),
    )
    assert center[2] - 3.0 == pytest.approx(math.sqrt(3))
    assert center[2] - 3.0 != pytest.approx(2.0)


@pytest.mark.parametrize(
    "quaternion",
    [
        (0.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 2.0),
        (0.0, 0.0, float("nan"), 1.0),
        (0.0, 0.0, 1.0),
    ],
)
def test_bad_rotation_rejected(quaternion):
    """Do not silently normalize a missing or malformed calibration."""
    with pytest.raises(ValueError):
        rotation(quaternion)


@pytest.mark.parametrize(
    "point",
    [
        (0.0, 0.0, 0.0),
        (0.0, 0.0, -1.0),
        (float("inf"), 0.0, 1.0),
    ],
)
def test_invalid_observation_rejected(point):
    """Behind-camera and nonfinite points never produce guidance."""
    with pytest.raises(ValueError):
        transform(
            point,
            (0.0, 0.0, 0.0, 1.0),
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
        )
