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

"""Bounded reliable reader consume pauses, not a simulated DDS network outage."""

import importlib.util
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "depth,pause,diagnostics",
    [
        (1, 0.25, True),
        (10, 0.25, True),
        (100, 0.25, True),
        (10, 0.34, True),
        (10, 0.25, False),
    ],
)
def test_reliable_reader_pause_measures_publication(
    depth, pause, diagnostics, monkeypatch
):
    """Compare actual segments without assuming slow consumption blocks DDS ACKs."""
    path = Path(__file__).with_name("test_frame_timing_ros.py")
    spec = importlib.util.spec_from_file_location(
        "publication_frame_fixture", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = module.run_frame_experiment(
        "collector_delay",
        monkeypatch,
        reader_depth=depth,
        diagnostics=diagnostics,
        pause_duration=pause,
        freeze_profile=True,
        publication_limit_s=None,
        expect_no_reset=False,
    )
    assert report["reader_qos"] == {
        "depth": depth,
        "reliability": "RELIABLE",
        "durability": "VOLATILE",
    }
    assert report["profile"]["sha256"]
    assert report["exit"] == 0 and not report["forced"]
    if diagnostics:
        samples = report["analysis"]["samples"]
        assert samples
        assert all(sample["publication_ms"] >= 0 for sample in samples)
        # Measurements remain measurements: no fabricated queue duration for
        # unavailable native timestamps and no a priori backpressure verdict.
        assert all(
            sample["native_receive_to_take_ms"] is None
            or sample["native_receive_to_take_ms"] >= 0
            for sample in samples
        )
    else:
        assert report["analysis"]["internal_stages"] is None
