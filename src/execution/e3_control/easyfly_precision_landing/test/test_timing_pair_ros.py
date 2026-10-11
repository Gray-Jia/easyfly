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

"""Only real observation-node DDS pairing; no flight, Action or simulation."""

import json
import math
import signal
import subprocess
import time

from ament_index_python.packages import get_package_prefix
from easyfly_msgs.msg import LandingGuidanceTarget, LandingTarget, UAVState
from easyfly_msgs.srv import GetCapabilities
import pytest
import rclpy
from rosgraph_msgs.msg import Clock


@pytest.mark.parametrize(
    "case", ["late_valid", "receipt_expired", "history_newest_safe"]
)
def test_late_vehicle_state_cannot_renew_source(case, tmp_path, monkeypatch):
    """Separate advancing source time from original steady-receipt expiration."""
    monkeypatch.setenv("ROS_DOMAIN_ID", "198")
    rclpy.init()
    peer = rclpy.create_node("timing_pair_peer_" + case)
    clock_pub = peer.create_publisher(Clock, "/clock", 10)
    states = peer.create_publisher(UAVState, "/uav_state", 10)
    targets = peer.create_publisher(LandingTarget, "/landing_target", 10)
    capability = peer.create_client(
        GetCapabilities, "/platform/precision_observation/capabilities"
    )
    seen, evidence = [], []
    started = time.monotonic()

    def receive(message):
        seen.append(message)
        evidence.append(
            {
                "elapsed_s": time.monotonic() - started,
                "valid": message.valid,
                "reason": message.reason,
                "stamp_ns": message.header.stamp.sec * 1000000000
                + message.header.stamp.nanosec,
                "source_ns": message.source_header.stamp.sec * 1000000000
                + message.source_header.stamp.nanosec,
            }
        )

    peer.create_subscription(
        LandingGuidanceTarget, "/landing/guidance_target", receive, 10
    )
    log = (tmp_path / "node.log").open("w")
    root = math.sqrt(0.5)
    binary = (
        get_package_prefix("easyfly_precision_landing")
        + "/lib/easyfly_precision_landing/landing_transform_node"
    )
    process = subprocess.Popen(
        [
            binary,
            "--ros-args",
            "-r",
            "__node:=timing_transform_" + case,
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
        ],
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    now_ns = 100000000000

    def pump(seconds):
        nonlocal now_ns
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            assert process.poll() is None, "actual observation node exited"
            # ROS clock advances slowly; steady deadlines remain real elapsed time.
            now_ns += 100000
            clock = Clock()
            clock.clock.sec, clock.clock.nanosec = divmod(now_ns, 1000000000)
            clock_pub.publish(clock)
            rclpy.spin_once(peer, timeout_sec=0.005)

    def until(predicate, budget=2.0):
        end = time.monotonic() + budget
        while not predicate() and time.monotonic() < end:
            pump(0.01)
        assert predicate(), "DDS readiness/evidence deadline"

    def target(source):
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
        targets.publish(message)

    def state(source):
        message = UAVState(
            connected=True,
            pose_valid=True,
            attitude_valid=True,
            position_z=1.0,
        )
        message.header.frame_id = "odom"
        message.header.stamp.sec, message.header.stamp.nanosec = divmod(
            source, 1000000000
        )
        states.publish(message)

    try:
        until(
            lambda: targets.get_subscription_count() > 0
            and states.get_subscription_count() > 0
            and clock_pub.get_subscription_count() > 0
            and capability.service_is_ready()
        )
        pump(0.2)
        future = capability.call_async(GetCapabilities.Request())
        until(future.done)
        assert (
            future.result().header.stamp.sec > 0
        )  # actual node has consumed /clock
        seen.clear()
        original = now_ns
        target(original)
        until(
            lambda: any(
                m.reason == "vehicle_source_pair_pending" for m in seen
            )
        )
        assert not any(m.valid for m in seen)
        if case == "late_valid":
            pump(0.08)
            state(original)
            until(lambda: any(m.valid for m in seen), budget=0.15)
            good = next(m for m in seen if m.valid)
            assert good.header.stamp == good.source_header.stamp
            assert (
                good.header.stamp.sec * 1000000000 + good.header.stamp.nanosec
                == original
            )
        elif case == "receipt_expired":
            pump(0.36)
            assert (
                now_ns - original
            ) * 1e-9 < 0.3  # source still inside ROS-age bound
            state(original)
            pump(0.08)
            assert not any(m.valid for m in seen)
            assert any(m.reason == "expired_or_clock_invalid" for m in seen)
        else:
            newest = original + 150000000
            now_ns = newest
            target(newest)
            pump(0.04)
            # User-approved history pairs an older still-fresh source while
            # the newer source waits; the state never authorizes the new frame.
            state(original)
            pump(0.05)
            valid = [m for m in seen if m.valid]
            assert valid and all(
                m.header.stamp.sec * 1000000000 + m.header.stamp.nanosec
                == original for m in valid
            )
            state(newest)
            until(
                lambda: any(
                    m.valid and m.header.stamp.sec * 1000000000
                    + m.header.stamp.nanosec == newest for m in seen
                ), budget=0.1
            )
            valid = [m for m in seen if m.valid]
            sources = [m.header.stamp.sec * 1000000000 + m.header.stamp.nanosec
                       for m in valid]
            assert sources == [original, newest]
            seen.clear()
            pump(0.35)
            state(original)
            pump(0.06)
            assert not any(
                m.valid for m in seen
            ), "old state must not renew a published target"
            assert any(m.reason == "expired_or_clock_invalid" for m in seen)
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
        forced = False
        try:
            process.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            forced = True
            process.kill()
            process.wait(timeout=3.0)
        log.close()
        (tmp_path / "evidence.json").write_text(
            json.dumps(
                {
                    "case": case,
                    "exit": process.returncode,
                    "forced": forced,
                    "outputs": evidence,
                },
                indent=2,
            )
        )
        print("timing_pair_evidence " + str(tmp_path))
        peer.destroy_node()
        rclpy.shutdown()
        assert not forced and process.returncode == 0
