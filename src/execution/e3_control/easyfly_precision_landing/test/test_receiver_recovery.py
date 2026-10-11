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

"""Real Node, controlled steady scheduling; no spin, flight or wall admission."""

import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace

from easyfly_msgs.msg import LandingTarget, UAVState
from easyfly_msgs.srv import GetCapabilities
import pytest
import rclpy
from rclpy.qos import DurabilityPolicy, ReliabilityPolicy
from rclpy.time import Time


@pytest.fixture
def receiver(monkeypatch):
    """Use actual receiver code with independently controlled ROS/steady clocks."""
    monkeypatch.setenv("ROS_DOMAIN_ID", "202")
    path = (
        Path(__file__).resolve().parents[1]
        / "easyfly_precision_landing/node.py"
    )
    spec = importlib.util.spec_from_file_location(
        "easyfly_precision_landing.recovery_node", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    clock = {"steady": 100.0, "ros": 10000000000}
    monkeypatch.setattr(module.time, "monotonic", lambda: clock["steady"])

    def forbidden_wall():
        raise AssertionError("wall time cannot authorize receiver recovery")

    monkeypatch.setattr(module.time, "time", forbidden_wall)
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
                now=lambda: Time(nanoseconds=clock["ros"])
            ),
        )
        outputs = []
        monkeypatch.setattr(node.publisher, "publish", outputs.append)
        yield node, clock, outputs
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


def vehicle(source):
    """Return a trusted geometry state, not a command or fabricated flight goal."""
    state = UAVState(
        connected=True, pose_valid=True, attitude_valid=True, position_z=1.0
    )
    state.header.frame_id = "odom"
    state.header.stamp.sec, state.header.stamp.nanosec = divmod(
        source, 1000000000
    )
    return state


def observation(source):
    """Return explicit metric fixed-down-camera synthetic perception only."""
    target = LandingTarget(
        tag_id=7,
        tag_size_m=0.2,
        valid=True,
        optical_depth_m=1.0,
        reprojection_error_px=0.2,
    )
    target.header.frame_id = "camera_down_optical_frame"
    target.header.stamp.sec, target.header.stamp.nanosec = divmod(
        source, 1000000000
    )
    target.pose.position.z = 1.0
    target.pose.orientation.w = 1.0
    return target


def prime_pending(node, clock, outputs):
    """Retain a real valid result, then one new source awaiting its state."""
    initial = clock["ros"]
    node.receive_state(vehicle(initial), node.generation)
    node.receive_target(observation(initial), node.generation)
    assert outputs[-1].valid
    clock["steady"] += 0.01
    clock["ros"] += 150000000
    node.receive_target(observation(clock["ros"]), node.generation)
    assert node.pending is not None
    return node.watermark


@pytest.mark.parametrize("entry", ["state", "target", "watchdog"])
def test_any_first_entry_resets_and_reacquires(receiver, entry):
    """Drop the gap trigger, purge old evidence, then accept genuinely new input."""
    node, clock, outputs = receiver
    watermark = prime_pending(node, clock, outputs)
    old_generation = node.generation
    old_state, old_target = node.state_sub, node.target_sub
    clock["steady"] += 0.31
    clock["ros"] += 10000000
    outputs.clear()
    if entry == "state":
        node.receive_state(vehicle(clock["ros"]), old_generation)
    elif entry == "target":
        node.receive_target(observation(clock["ros"]), old_generation)
    else:
        node.watchdog()
    assert node.generation == old_generation + 1
    assert node.reset_count == 1
    assert not node.states and node.pending is None and node.last_good is None
    assert node.last_receipt == 0.0
    assert node.watermark >= watermark
    assert (
        node.state_sub is not old_state and node.target_sub is not old_target
    )
    assert node.state_sub.qos_profile.durability == DurabilityPolicy.VOLATILE
    assert node.target_sub.qos_profile.durability == DurabilityPolicy.VOLATILE
    assert node.target_sub.qos_profile.reliability == ReliabilityPolicy.BEST_EFFORT
    assert node.target_sub.qos_profile.depth == 1
    assert node.state_sub.qos_profile.reliability == ReliabilityPolicy.RELIABLE
    assert node.state_sub.qos_profile.depth == 10
    assert node.publisher.qos_profile.reliability == ReliabilityPolicy.RELIABLE
    assert node.publisher.qos_profile.depth == 1
    assert outputs and all(not message.valid for message in outputs)
    assert outputs[-1].reason == "receiver_processing_gap"
    # Cached executor callbacks from destroyed readers cannot revive the pending input.
    outputs.clear()
    node.receive_state(vehicle(watermark), old_generation)
    node.receive_target(observation(watermark), old_generation)
    assert not outputs and not node.states and node.pending is None
    clock["steady"] += 0.01
    clock["ros"] = max(clock["ros"], node.watermark) + 10000000
    fresh = clock["ros"]
    node.receive_state(vehicle(fresh), node.generation)
    node.receive_target(observation(fresh), node.generation)
    assert outputs[-1].valid
    assert outputs[-1].source_header == observation(fresh).header
    outputs.clear()
    node.receive_target(observation(watermark), node.generation)
    assert outputs and all(not message.valid for message in outputs)
    assert node.watermark == fresh


def test_old_generation_has_no_side_effect_on_new_evidence(receiver):
    """Ignore queued old readers even when new trusted evidence already exists."""
    node, clock, outputs = receiver
    node.receive_state(vehicle(clock["ros"]), node.generation)
    node.receive_target(observation(clock["ros"]), node.generation)
    old = node.generation
    clock["steady"] += 0.31
    node.watchdog()
    clock["steady"] += 0.01
    clock["ros"] += 20000000
    node.receive_state(vehicle(clock["ros"]), node.generation)
    node.receive_target(observation(clock["ros"]), node.generation)
    assert outputs[-1].valid
    good, watermark, receipt, tick = (
        node.last_good,
        node.watermark,
        node.last_receipt,
        node.last_processing,
    )
    states = list(node.states)
    outputs.clear()
    clock["steady"] += .01
    node.receive_state(UAVState(), old)
    node.receive_target(observation(clock["ros"] + 100000000), old)
    assert not outputs
    assert node.last_good is good and list(node.states) == states
    assert node.watermark == watermark and node.last_receipt == receipt
    assert node.last_processing == tick and node.reset_count == 1


@pytest.mark.parametrize("entry", ["state", "target", "watchdog"])
def test_within_processing_budget_keeps_readers(receiver, entry):
    """Ordinary callbacks within the steady budget do not reconstruct readers."""
    node, clock, outputs = receiver
    state_sub, target_sub = node.state_sub, node.target_sub
    clock["steady"] += 0.29
    if entry == "state":
        node.receive_state(vehicle(clock["ros"]), node.generation)
    elif entry == "target":
        node.receive_target(observation(clock["ros"]), node.generation)
    else:
        node.watchdog()
    assert node.generation == 0 and node.reset_count == 0
    assert node.state_sub is state_sub and node.target_sub is target_sub
    assert not any(m.reason == "receiver_processing_gap" for m in outputs)


def test_capability_queries_cannot_renew_continuity(receiver):
    """Frequent readiness queries cannot hide a stopped processing path."""
    node, clock, outputs = receiver
    node.receive_state(vehicle(clock["ros"]), node.generation)
    node.receive_target(observation(clock["ros"]), node.generation)
    processed = node.last_processing
    for _ in range(2):
        clock["steady"] += .1
        clock["ros"] += 10000000
        response = node.capabilities(
            GetCapabilities.Request(), GetCapabilities.Response()
        )
        assert response.ready == [True]
        assert node.last_processing == processed and node.reset_count == 0
    clock["steady"] += .11
    response = node.capabilities(
        GetCapabilities.Request(), GetCapabilities.Response()
    )
    assert response.ready == [False]
    assert node.reset_count == 1 and node.last_good is None
    assert outputs[-1].reason == "receiver_processing_gap"


def test_reader_rebuild_failure_never_publishes_valid(receiver, monkeypatch):
    """Surface reconstruction errors only after invalidating all old evidence."""
    node, clock, outputs = receiver
    prime_pending(node, clock, outputs)
    old = node.generation

    def unavailable():
        raise RuntimeError("injected reader creation failure")

    monkeypatch.setattr(node, "create_receivers", unavailable)
    clock["steady"] += .31
    outputs.clear()
    with pytest.raises(RuntimeError, match="injected reader creation failure"):
        node.watchdog()
    assert not node.states and node.pending is None and node.last_good is None
    assert node.last_receipt == 0.0 and node.generation == old + 1
    assert outputs and all(not message.valid for message in outputs)
    outputs.clear()
    node.receive_target(observation(clock["ros"]), old)
    assert not outputs


def test_far_future_gap_trigger_does_not_poison_watermark(receiver):
    """Reject malformed future evidence without preventing ordinary reacquisition."""
    node, clock, outputs = receiver
    previous = prime_pending(node, clock, outputs)
    clock["steady"] += .31
    node.receive_target(observation(clock["ros"] + 1000000000), node.generation)
    assert node.watermark == previous and node.reset_count == 1
    clock["steady"] += .01
    clock["ros"] += 10000000
    node.receive_state(vehicle(clock["ros"]), node.generation)
    node.receive_target(observation(clock["ros"]), node.generation)
    assert outputs[-1].valid


def test_steady_rewind_also_discards_evidence(receiver):
    """A negative local interval is invalid, not renewed freshness."""
    node, clock, outputs = receiver
    prime_pending(node, clock, outputs)
    clock["steady"] -= .1
    outputs.clear()
    node.watchdog()
    assert node.reset_count == 1 and node.last_good is None
    assert not node.states and node.pending is None
    assert outputs and all(not message.valid for message in outputs)
