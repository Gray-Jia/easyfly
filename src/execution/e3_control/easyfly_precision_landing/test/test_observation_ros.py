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

"""Actual node process: pairing, stale data, replay and signal shutdown."""

import math
import json
import os
import signal
import subprocess
import time

from ament_index_python.packages import get_package_prefix
from easyfly_msgs.msg import LandingGuidanceTarget, LandingTarget, UAVState
import pytest
import rclpy
from rosgraph_msgs.msg import Clock
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy


@pytest.mark.parametrize("stop_signal", [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize("reliability", [
    ReliabilityPolicy.RELIABLE, ReliabilityPolicy.BEST_EFFORT,
])
def test_actual_observation_node(stop_signal, reliability, tmp_path):
    """Verify real DDS outputs and process exit, not graph presence alone."""
    rclpy.init()
    fixture = rclpy.create_node("landing_observation_fixture")
    seen = []
    clock_pub = fixture.create_publisher(Clock, "/clock", 10)
    state_pub = fixture.create_publisher(UAVState, "/uav_state", 10)
    target_pub = fixture.create_publisher(
        LandingTarget, "/landing_target",
        QoSProfile(depth=1, reliability=reliability),
    )
    fixture.create_subscription(
        LandingGuidanceTarget, "/landing/guidance_target", seen.append, 10
    )
    binary = (
        get_package_prefix("easyfly_precision_landing")
        + "/lib/easyfly_precision_landing/landing_transform_node"
    )
    root = math.sqrt(0.5)
    args = [
        binary,
        "--ros-args",
        "-p",
        "use_sim_time:=true",
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
    diagnostics = stop_signal == signal.SIGTERM
    if diagnostics:
        args += ["-p", "diagnostics:=true"]
    # Structured diagnostics and ROS shutdown errors must not share a byte
    # stream. Drain to files rather than filling a pipe while the node runs.
    stdout_path, stderr_path = tmp_path / 'observation.log', tmp_path / 'errors.log'
    stdout_stream, stderr_stream = stdout_path.open('w'), stderr_path.open('w')
    process = subprocess.Popen(args, stdout=stdout_stream, stderr=stderr_stream,
                               env={**os.environ, 'RCUTILS_LOGGING_USE_STDOUT': '1'})
    now_ns = 10000000000

    def pump(predicate, budget=3.0):
        deadline = time.monotonic() + budget
        while time.monotonic() < deadline and process.poll() is None:
            clock = Clock()
            clock.clock.sec, clock.clock.nanosec = divmod(now_ns, 1000000000)
            clock_pub.publish(clock)
            rclpy.spin_once(fixture, timeout_sec=0.01)
            if predicate():
                return
        assert predicate(), "observation output or process readiness deadline"

    def inputs(
        frame="camera_down_optical_frame",
        tag_id=7,
        valid=True,
        publish_state=True,
    ):
        state = UAVState()
        state.header.frame_id = "odom"
        state.header.stamp.sec, state.header.stamp.nanosec = divmod(
            now_ns, 1000000000
        )
        state.connected = state.pose_valid = state.attitude_valid = True
        state.position_z = 1.0
        if publish_state:
            state_pub.publish(state)
        target = LandingTarget()
        target.header.stamp = state.header.stamp
        target.header.frame_id = frame
        target.tag_id = tag_id
        target.tag_size_m = 0.2
        target.valid = valid
        target.pose.position.x = 0.2
        target.pose.position.y = -0.1
        target.pose.position.z = target.optical_depth_m = 1.0
        target.pose.orientation.w = 1.0
        target.reprojection_error_px = 0.2
        target_pub.publish(target)
        return target

    try:
        pump(
            lambda: target_pub.get_subscription_count() > 0
            and state_pub.get_subscription_count() > 0
            and any(
                item.node_name == "landing_transform"
                for item in fixture.get_subscriptions_info_by_topic("/landing_target")
            )
        )
        readers = fixture.get_subscriptions_info_by_topic("/landing_target")
        reader = next(item for item in readers if item.node_name == "landing_transform")
        assert reader.qos_profile.reliability == ReliabilityPolicy.BEST_EFFORT
        assert reader.qos_profile.durability == DurabilityPolicy.VOLATILE
        # Allow clock/state delivery before the target; all are real DDS inputs.
        inputs(valid=False)
        pump(lambda: any(not message.valid for message in seen))
        seen.clear()
        now_ns += 10000000
        inputs()
        pump(lambda: any(message.valid for message in seen))
        good = next(message for message in seen if message.valid)
        assert (
            good.position.x,
            good.position.y,
            good.position.z,
        ) == pytest.approx((0.1, -0.2, 0.0))
        assert good.source_header.frame_id == "camera_down_optical_frame"
        assert good.header.frame_id == "odom" and good.tag_id == 7
        seen.clear()
        inputs()
        pump(
            lambda: any(
                message.reason == "source_invalid_or_replayed"
                for message in seen
            )
        )
        assert not any(message.valid for message in seen)
        for frame, identity in [
            ("wrong_optical_frame", 7),
            ("camera_down_optical_frame", 8),
        ]:
            seen.clear()
            now_ns += 10000000
            inputs(frame=frame, tag_id=identity)
            pump(
                lambda: any(
                    message.reason == "source_invalid_or_replayed"
                    for message in seen
                )
            )
            assert not any(message.valid for message in seen)
        seen.clear()
        now_ns += 10000000
        inputs()
        pump(lambda: any(message.valid for message in seen))
        seen.clear()
        now_ns += 200000000
        delayed = inputs(publish_state=False)
        end = time.monotonic() + 0.06
        pump(lambda: time.monotonic() >= end, budget=0.2)
        assert not any(
            message.valid and message.header.stamp == delayed.header.stamp
            for message in seen
        )
        matched = UAVState()
        matched.header.frame_id = "odom"
        matched.header.stamp = delayed.header.stamp
        matched.connected = matched.pose_valid = matched.attitude_valid = True
        matched.position_z = 1.0
        state_pub.publish(matched)
        pump(
            lambda: any(
                message.valid and message.header.stamp == delayed.header.stamp
                for message in seen
            )
        )
        paired = next(message for message in seen if message.valid)
        assert paired.source_header.stamp == delayed.header.stamp
        seen.clear()
        now_ns += 200000000
        expired = inputs(publish_state=False)
        pump(
            lambda: any(
                message.reason == "expired_or_clock_invalid"
                for message in seen
            )
        )
        seen.clear()
        now_ns += 400000000
        matched.header.stamp.sec, matched.header.stamp.nanosec = divmod(
            now_ns, 1000000000
        )
        state_pub.publish(matched)
        end = time.monotonic() + 0.06
        pump(lambda: time.monotonic() >= end, budget=0.2)
        assert not any(
            message.valid and message.header.stamp == expired.header.stamp
            for message in seen
        )
        seen.clear()
        now_ns += 10000000
        inputs()
        pump(lambda: any(message.valid for message in seen))
        seen.clear()
        # Keep positive /clock frozen. No new target/state may refresh evidence.
        pump(
            lambda: any(
                message.reason == "expired_or_clock_invalid"
                for message in seen
            )
        )
        assert not any(message.valid for message in seen)
        if diagnostics:
            end = time.monotonic() + 1.1
            pump(lambda: time.monotonic() >= end, budget=1.5)
        process.send_signal(stop_signal)
        process.wait(timeout=2.0)
        output = stdout_path.read_text()
        errors = stderr_path.read_text()
        assert process.returncode == 0, output + errors
        print('node stderr retained separately:', errors)
        records = [
            json.loads(line.split("landing_diag ", 1)[1])
            for line in output.splitlines()
            if "landing_diag " in line
        ]
        if diagnostics:
            assert records
            record = records[-1]
            assert record["counts"]["target"] > 0
            assert record["counts"]["state"] > 0
            assert record["counts"]["publish_valid"] > 0
            assert record["counts"]["publish_invalid"] > 0
            assert record["max_wall_ms"]["publish"] >= 0
            assert record["max_wall_ms"]["target"] >= 0
            assert record["latest_source"]["target"]["stamp_ns"] > 0
            assert record["state_count"] <= 64
            assert record["rmw_timing"]["/landing_target"]["source_wall_ns"] > 0
            assert record["rmw_timing"]["/landing_target"]["take_wall_ns"] > 0
            assert record["pairing"]["max_wait_ms"] >= 0
            assert len(records) <= record["counts"]["watchdog"] / 15 + 1
        else:
            assert not records
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.communicate(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
        stdout_stream.close()
        stderr_stream.close()
        fixture.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
