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

"""Offline calibration/hash/state ambiguity regression, with no ROS processes."""

import hashlib
import importlib.util
import json
import math
from pathlib import Path

from PIL import Image
import pytest


SPEC = importlib.util.spec_from_file_location(
    "replay_tag_frames", Path(__file__).resolve().parents[1] / "scripts/replay_tag_frames.py"
)
REPLAY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPLAY)


def test_captured_nested_camera_info_preserves_other_run_provenance(tmp_path):
    """Real K input remains a capture, not certification for historical frames."""
    model = {"k": [337.0, 0.0, 320.5, 0.0, 337.0, 240.5, 0.0, 0.0, 1.0], "d": [0.0] * 5}
    source = tmp_path / "captured.json"
    source.write_text(json.dumps({"observation_samples": [{"camera_info": model}] * 3}))
    result = REPLAY.load_calibrations(tmp_path, source)
    assert len(result) == 1 and result[0]["K"] == model["k"]
    assert result[0]["D"] == model["d"]
    assert not result[0]["same_run_calibration_certified"]


def test_sdf_calibration_is_explicit_assumption(tmp_path):
    """Only geometry determines focal length; principal-point guesses stay labeled."""
    (tmp_path / "down_iris.sdf").write_text(
        '<sdf><sensor name="down_color"><camera>'
        "<horizontal_fov>1.518</horizontal_fov><image><width>640</width><height>480</height>"
        "</image></camera></sensor></sdf>"
    )
    result = REPLAY.load_calibrations(tmp_path)
    assert [item["K"][2] for item in result] == [320.0, 319.5]
    assert result[0]["K"][0] == pytest.approx(640 / (2 * math.tan(1.518 / 2)))
    assert all("NOT captured" in item["provenance"] for item in result)


def test_raw_hash_and_capture_index_are_both_required(tmp_path):
    """Keep all source matches if repeated pixels do not certify a capture index."""
    raw = bytes([1, 2, 3, 4, 5, 6])
    image = tmp_path / "camera_0030.png"
    Image.frombytes("RGB", (2, 1), raw).save(image)
    digest = hashlib.sha256(raw).hexdigest()
    samples = [{"source_ns": i, "image_sha256": digest} for i in range(30)]
    hashes, match, reason = REPLAY.image_sources(image, {"observation_samples": samples})
    assert hashes["rgb8"] == digest and match == [samples[-1]]
    assert reason == "capture_index_and_exact_raw_hash"
    samples[-1]["image_sha256"] = "mismatch"
    _, match, reason = REPLAY.image_sources(image, {"observation_samples": samples})
    assert len(match) == 29 and "ambiguity" in reason


def test_same_ros_stamp_states_are_an_envelope_not_a_guessed_receipt():
    """A height disagreement at one stamp must retain both classification hypotheses."""
    root = math.sqrt(0.5)
    config = {
        "camera_translation_flu": [0.0, 0.0, 0.0],
        "camera_quaternion_xyzw": [root, -root, 0.0, 0.0],
        "landing_plane_z_m": 0.0,
        "plane_height_tolerance_m": 0.15,
        "plane_tilt_limit_rad": 0.175,
    }
    state = {"stamp": 10.0, "x": 0.0, "y": 0.0, "z": 1.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}
    other = dict(state, z=1.2)
    candidate = {"translation": [0.0, 0.0, 1.0], "quaternion": [0.0, 0.0, 0.0, 1.0]}
    result = REPLAY.state_envelope(10000000000, [state, other], candidate, config)
    assert len(result["states"]) == len(result["geometry_hypotheses"]) == 2
    assert result["receipt_and_actual_pair_unknown"]
    assert [item["height_rejected"] for item in result["geometry_hypotheses"]] == [False, True]
    assert not any(item["tilt_rejected"] for item in result["geometry_hypotheses"])
    far = REPLAY.state_envelope(10200000000, [state], candidate, config)
    assert not far["within_pair_gap"] and "geometry_hypotheses" not in far


@pytest.mark.parametrize(
    "K,D",
    [
        ([0.0] * 9, []),
        ([1.0] * 8, []),
        ([337.0, 0.0, 320.0, 0.0, 337.0, 240.0, 0.0, 0.0, 1.0], [float("nan")] * 5),
    ],
)
def test_invalid_calibration_never_becomes_an_assumed_valid_model(tmp_path, K, D):
    """Reject malformed input instead of silently replacing measured calibration."""
    source = tmp_path / "bad.json"
    source.write_text(json.dumps({"K": K, "D": D}))
    with pytest.raises(ValueError):
        REPLAY.load_calibrations(tmp_path, source)
