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

"""Controlled real Node history safety; no spin, flight or wall-time admission."""

import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace

from easyfly_msgs.msg import LandingTarget, UAVState
import pytest
import rclpy


@pytest.fixture
def history(monkeypatch):
    """Run source receiver logic with separate controllable ROS/steady domains."""
    monkeypatch.setenv("ROS_DOMAIN_ID", "206")
    path = (
        Path(__file__).resolve().parents[1]
        / "easyfly_precision_landing/node.py"
    )
    spec = importlib.util.spec_from_file_location(
        "easyfly_precision_landing.history_node", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    clock = {"steady": 100.0, "ros": 10000000000}
    monkeypatch.setattr(module.time, "monotonic", lambda: clock["steady"])
    root = math.sqrt(0.5)
    rclpy.init(
        args=[
            "--ros-args",
            "-p",
            "configured:=true",
            "-p",
            "selected_tag_id:=7",
            "-p",
            "tag_size_m:=0.2",
            "-p",
            "landing_plane_z_m:=0.0",
            "-p",
            f"camera_quaternion_xyzw:=[{root}, {-root}, 0.0, 0.0]",
        ]
    )
    node = None
    try:
        node = module.LandingTransform()
        monkeypatch.setattr(
            node,
            "get_clock",
            lambda: SimpleNamespace(
                now=lambda: SimpleNamespace(nanoseconds=clock["ros"])
            ),
        )
        outputs = []
        monkeypatch.setattr(node.publisher, "publish", outputs.append)
        yield node, clock, outputs
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


def target(source):
    """Produce metric fixed-camera perception, not flight commands."""
    message = LandingTarget(
        tag_id=7,
        tag_size_m=0.2,
        valid=True,
        optical_depth_m=1.0,
        reprojection_error_px=0.2,
    )
    message.header.frame_id = "camera_down_optical_frame"
    message.header.stamp.sec, message.header.stamp.nanosec = divmod(
        source, 1000000000
    )
    message.pose.position.z = 1.0
    message.pose.orientation.w = 1.0
    return message


def state(source):
    """Produce trusted synthetic transform geometry without aircraft dynamics."""
    message = UAVState(
        connected=True, pose_valid=True, attitude_valid=True, position_z=1.0
    )
    message.header.frame_id = "odom"
    message.header.stamp.sec, message.header.stamp.nanosec = divmod(
        source, 1000000000
    )
    return message


def sources(node):
    """Read retained original sources and receipts without changing evidence."""
    return [
        (m.header.stamp.sec * 1000000000 + m.header.stamp.nanosec, receipt)
        for m, receipt in node.pending_sources
    ]


def enqueue(node, clock, source):
    """Supply one strictly newer source with a genuine first receipt."""
    clock["ros"] = source
    node.receive_target(target(source), node.generation)


def test_capacity_evicts_oldest_without_renewing_retained_receipts(history):
    """At most 32 source frames survive; each keeps its original receipt."""
    node, clock, outputs = history
    expected = []
    for index in range(40):
        clock["steady"] = 100.0 + index * 0.001
        source = 10000000000 + index * 1000000
        expected.append((source, clock["steady"]))
        enqueue(node, clock, source)
    assert node.pending_sources.maxlen == 32
    assert sources(node) == expected[-32:]
    assert not any(m.valid for m in outputs)


@pytest.mark.parametrize("kind", ["height", "tilt"])
def test_geometry_rejection_records_the_actual_gate_without_relaxing_it(history, kind):
    """Trace the selected exact state and distinguish plane gates, still invalid."""
    node, clock, outputs = history
    node.diagnostics = True
    message = target(clock["ros"])
    if kind == "height":
        message.pose.position.z = message.optical_depth_m = 0.8
    else:
        message.pose.orientation.x = math.sin(0.15)
        message.pose.orientation.w = math.cos(0.15)
    node.receive_state(state(clock["ros"]), node.generation)
    node.receive_target(message, node.generation)
    assert not any(item.valid for item in outputs)
    selected = [item for item in node.diag_events if item["stage"] == "pair_selected"]
    rejected = [item for item in node.diag_events if item["stage"] == "geometry_rejected"]
    assert len(selected) == len(rejected) == 1
    assert selected[0]["vehicle_position"] == [0.0, 0.0, 1.0]
    assert rejected[0]["height_exceeded"] is (kind == "height")
    assert rejected[0]["tilt_exceeded"] is (kind == "tilt")
    assert rejected[0]["plane_tolerance_m"] == 0.15
    assert rejected[0]["tilt_limit_rad"] == 0.175


def test_expired_old_source_removed_but_new_source_retains_original_receipt(
    history,
):
    """Steady-expired input cannot crowd out a still-live newer observation."""
    node, clock, outputs = history
    enqueue(node, clock, 10000000000)
    clock["steady"] = 100.2
    enqueue(node, clock, 10200000000)
    clock["steady"] = 100.31
    clock["ros"] = 10250000000
    node.watchdog()
    assert sources(node) == [(10200000000, 100.2)]
    assert not any(m.valid for m in outputs)


def test_repeated_pair_attempts_do_not_refresh_original_receipt(history):
    """A matching late state does not revive a target after its first TTL."""
    node, clock, outputs = history
    enqueue(node, clock, 10000000000)
    for steady in (100.1, 100.2, 100.29):
        clock["steady"] = steady
        clock["ros"] = 10100000000
        node.watchdog()
        assert sources(node) == [(10000000000, 100.0)]
    clock["steady"] = 100.31
    clock["ros"] = 10120000000
    node.receive_state(state(10050000000), node.generation)
    assert not node.pending_sources and not any(m.valid for m in outputs)


def test_latest_matchable_output_monotonic_with_newer_pending_preserved(
    history,
):
    """Pair the latest eligible source, purge older ones and never output backwards."""
    node, clock, outputs = history
    for source in (10000000000, 10150000000, 10250000000):
        clock["steady"] += 0.01
        enqueue(node, clock, source)
    node.receive_state(state(10100000000), node.generation)
    assert outputs[-1].valid and node.published_watermark == 10150000000
    assert [source for source, _ in sources(node)] == [10250000000]
    node.receive_state(state(10250000000), node.generation)
    assert outputs[-1].valid and node.published_watermark == 10250000000
    count = sum(m.valid for m in outputs)
    node.receive_state(state(10000000000), node.generation)
    assert sum(m.valid for m in outputs) == count
    node.receive_target(target(10150000000), node.generation)
    assert not outputs[-1].valid and not node.pending_sources


def test_no_match_never_blindly_uses_an_old_frame(history):
    """Freshness alone does not authorize an out-of-window geometry pair."""
    node, clock, outputs = history
    for source in (10200000000, 10250000000):
        enqueue(node, clock, source)
    clock["ros"] = 10450000000
    node.receive_state(state(clock["ros"]), node.generation)
    assert not any(m.valid for m in outputs)
    assert len(node.pending_sources) == 2


@pytest.mark.parametrize(
    "event", ["bad_target", "bad_quality", "bad_frame", "wrong_id",
              "bad_state", "geometry", "rewind", "frozen_clock", "reader_reset"]
)
def test_invalid_new_evidence_and_epoch_changes_purge_history(history, event):
    """Never try older frames after invalidity, geometric failure or reader reset."""
    node, clock, outputs = history
    for source in (10000000000, 10150000000):
        enqueue(node, clock, source)
    assert len(node.pending_sources) == 2
    outputs.clear()
    if event == "bad_target":
        invalid = target(10200000000)
        invalid.valid = False
        node.receive_target(invalid, node.generation)
    elif event in ("bad_quality", "bad_frame", "wrong_id"):
        invalid = target(10200000000)
        if event == "bad_quality":
            invalid.pose.orientation.w = 0.0
        elif event == "bad_frame":
            invalid.header.frame_id = "other_camera"
        else:
            invalid.tag_id = 8
        node.receive_target(invalid, node.generation)
    elif event == "bad_state":
        node.receive_state(UAVState(), node.generation)
    elif event == "geometry":
        clock["ros"] = 10250000000
        malformed = target(clock["ros"])
        malformed.pose.position.z = malformed.optical_depth_m = 3.0
        node.receive_target(malformed, node.generation)
        node.receive_state(state(clock["ros"]), node.generation)
    elif event == "rewind":
        clock["ros"] = 5000000000
        node.watchdog()
    elif event == "frozen_clock":
        for tick in (100.1, 100.2, 100.31):
            clock["steady"] = tick
            node.watchdog()
        assert node.reset_count == 0
    else:
        clock["steady"] += 0.31
        node.watchdog()
        assert node.reset_count == 1
    assert not node.pending_sources and node.pending is None
    assert node.last_good is None
    assert not any(m.valid for m in outputs)
