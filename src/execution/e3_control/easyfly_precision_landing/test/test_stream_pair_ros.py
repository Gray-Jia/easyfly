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

"""Continuous synthetic perception pairing only, without flight or simulation."""

from collections import Counter
import json
import math
from pathlib import Path
import signal
import subprocess
import tempfile
import time

from ament_index_python.packages import get_package_prefix
from easyfly_msgs.msg import LandingGuidanceTarget, LandingTarget, UAVState
from easyfly_msgs.srv import GetCapabilities
import pytest
import rclpy
from rosgraph_msgs.msg import Clock


@pytest.mark.parametrize(
    "case,state_lag,clock_offset",
    [
        ("matched", 0.02, 0.0),
        ("late_state", 0.16, 0.0),
        ("late_state_clock_phase", 0.16, 0.07),
    ],
)
@pytest.mark.parametrize("diagnostics", [False, True])
def test_continuous_source_stream_pairing(
    case, state_lag, clock_offset, diagnostics, monkeypatch
):
    """Measure coverage without treating an unavailable latest pair as authority."""
    monkeypatch.setenv("ROS_DOMAIN_ID", "205")
    workspace = Path(__file__).resolve().parents[5]
    artifacts = workspace / "artifacts/d5-pairing-20261006"
    artifacts.mkdir(parents=True, exist_ok=True)
    directory = Path(
        tempfile.mkdtemp(
            prefix=case + ("-diag-" if diagnostics else "-plain-"),
            dir=artifacts,
        )
    )
    report = {
        "case": case,
        "state_lag_s": state_lag,
        "target_lag_s": 0.02,
        "clock_offset_s": clock_offset,
        "diagnostics": diagnostics,
        "inputs": [],
        "outputs": [],
    }
    identity = case + ("_diag" if diagnostics else "_plain")
    rclpy.init()
    peer = rclpy.create_node("stream_pair_peer_" + identity)
    targets = peer.create_publisher(LandingTarget, "/landing_target", 1)
    states = peer.create_publisher(UAVState, "/uav_state", 10)
    clocks = peer.create_publisher(Clock, "/clock", 10)
    capabilities = peer.create_client(
        GetCapabilities, "/platform/precision_observation/capabilities"
    )
    steady_start = time.monotonic()
    clock_ns = 100000000000

    def received(message):
        source = (
            message.header.stamp.sec * 1000000000
            + message.header.stamp.nanosec
        )
        report["outputs"].append(
            {
                "elapsed_s": time.monotonic() - steady_start,
                "observer_arrival_steady_s": time.monotonic(),
                "valid": message.valid,
                "reason": message.reason,
                "source_ns": source,
                "observer_clock_ns": clock_ns,
                "ros_age_s": (clock_ns - source) * 1e-9 if source else None,
            }
        )

    peer.create_subscription(
        LandingGuidanceTarget, "/landing/guidance_target", received, 10
    )
    log = (directory / "node.log").open("w")
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
            "__node:=stream_pair_transform_" + identity,
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
            "diagnostics:=" + str(diagnostics).lower(),
            "-p",
            f"camera_quaternion_xyzw:=[{root}, {-root}, 0.0, 0.0]",
        ],
        stdout=log,
        stderr=subprocess.STDOUT,
    )

    def publish_clock(source):
        nonlocal clock_ns
        clock_ns = source
        clock = Clock()
        clock.clock.sec, clock.clock.nanosec = divmod(source, 1000000000)
        clocks.publish(clock)

    def spin(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            assert process.poll() is None
            rclpy.spin_once(peer, timeout_sec=0.005)

    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            publish_clock(100000000000)
            spin(0.02)
            if (
                targets.get_subscription_count()
                and states.get_subscription_count()
                and any(
                    info.node_name == "stream_pair_transform_" + identity
                    for info in peer.get_subscriptions_info_by_topic("/clock")
                )
                and capabilities.service_is_ready()
            ):
                break
        assert (
            targets.get_subscription_count()
            and states.get_subscription_count()
        )
        # Matching a reader does not prove that its first clock callback ran.
        # Read-only capability queries may be repeated; no goal is ever sent.
        deadline = time.monotonic() + 3
        ready = False
        while time.monotonic() < deadline:
            publish_clock(100000000000)
            spin(0.04)
            future = capabilities.call_async(GetCapabilities.Request())
            response_deadline = min(deadline, time.monotonic() + 0.5)
            while not future.done() and time.monotonic() < response_deadline:
                publish_clock(100000000000)
                spin(0.01)
            if future.done() and future.result().header.stamp.sec > 0:
                ready = True
                break
        assert ready, "actual observation node has not consumed initial /clock"
        report["outputs"].clear()
        run_start = time.monotonic()
        report["run_start_steady_s"] = run_start
        next_clock, next_state, next_target = clock_offset, 0.0, 0.0
        while time.monotonic() - run_start < 3.0:
            elapsed = time.monotonic() - run_start
            continuous = 100000000000 + round(elapsed * 1e9)
            if elapsed >= next_clock:
                publish_clock(continuous)
                next_clock += 0.1
            if elapsed >= next_state:
                state = UAVState(
                    connected=True,
                    pose_valid=True,
                    attitude_valid=True,
                    position_z=1.0,
                )
                state.header.frame_id = "odom"
                source = continuous - round(state_lag * 1e9)
                state.header.stamp.sec, state.header.stamp.nanosec = divmod(
                    source, 1000000000
                )
                states.publish(state)
                report["inputs"].append(
                    {
                        "kind": "state",
                        "source_ns": source,
                        "elapsed_s": elapsed,
                        "publish_steady_s": time.monotonic(),
                        "clock_ns": clock_ns,
                    }
                )
                next_state += 0.05
            if elapsed >= next_target:
                target = LandingTarget(
                    tag_id=7,
                    tag_size_m=0.2,
                    valid=True,
                    optical_depth_m=1.0,
                    reprojection_error_px=0.2,
                )
                target.header.frame_id = "camera_down_optical_frame"
                source = continuous - 20000000
                target.header.stamp.sec, target.header.stamp.nanosec = divmod(
                    source, 1000000000
                )
                target.pose.position.z = 1.0
                target.pose.orientation.w = 1.0
                targets.publish(target)
                report["inputs"].append(
                    {
                        "kind": "target",
                        "source_ns": source,
                        "elapsed_s": elapsed,
                        "publish_steady_s": time.monotonic(),
                        "clock_ns": clock_ns,
                    }
                )
                next_target += 1 / 30
            rclpy.spin_once(peer, timeout_sec=0.002)
        spin(0.04)
        valid = [item for item in report["outputs"] if item["valid"]]
        report["summary"] = {
            "target_count": sum(
                m["kind"] == "target" for m in report["inputs"]
            ),
            "state_count": sum(m["kind"] == "state" for m in report["inputs"]),
            "valid_count": len(valid),
            "reasons": dict(Counter(m["reason"] for m in report["outputs"])),
        }
        sources = [item["source_ns"] for item in valid]
        assert sources == sorted(
            set(sources)
        ), "no duplicate or decreasing valid source"
        assert all(-0.2 <= item["ros_age_s"] <= 0.3 for item in valid)
        required = 60 if case == "matched" else 50
        assert (
            len(valid) >= required
        ), "approved bounded pairing lacks continuous coverage"
        original = {
            m["source_ns"]: m
            for m in report["inputs"]
            if m["kind"] == "target"
        }
        for output in valid:
            target = original[output["source_ns"]]
            assert (
                0
                <= output["observer_arrival_steady_s"]
                - target["publish_steady_s"]
                <= 0.3
            )
            candidates = [
                m
                for m in report["inputs"]
                if m["kind"] == "state"
                and m["publish_steady_s"]
                <= output["observer_arrival_steady_s"]
            ]
            assert any(
                abs(m["source_ns"] - output["source_ns"]) <= 100000000
                for m in candidates
            ), "valid output lacks an actual input state within .1s"
        print(
            "stream_pair_summary " + json.dumps(report["summary"]), flush=True
        )
    except Exception as error:
        report["error"] = repr(error)
        raise
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
        forced = False
        try:
            process.wait(timeout=4.0)
        except subprocess.TimeoutExpired:
            forced = True
            process.kill()
            process.wait(timeout=3.0)
        report["exit"] = process.returncode
        report["forced"] = forced
        log.close()
        (directory / "evidence.json").write_text(json.dumps(report, indent=2))
        print("stream_pair_evidence " + str(directory), flush=True)
        peer.destroy_node()
        rclpy.shutdown()
        assert not forced and process.returncode == 0
