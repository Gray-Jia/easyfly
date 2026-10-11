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

"""Real observation/controller chain with explicit fake feedback, never SITL."""

import json
import math
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

from ament_index_python.packages import get_package_prefix
from easyfly_msgs.action import PrecisionLand, Takeoff
from easyfly_msgs.msg import (
    LandingGuidanceTarget,
    LandingTarget,
    UAVCommand,
    UAVState,
)
from easyfly_msgs.srv import (
    ArmMotors,
    GetActionOwnership,
    GetCapabilities,
    SetFlightMode,
)
import rclpy
from rclpy.action import ActionClient
from std_msgs.msg import Float64, String


def test_observation_reset_drives_real_precision_loss_and_recovery(
    monkeypatch,
):
    """Verify command behavior and actual terminal after observation reader reset."""
    monkeypatch.setenv("ROS_DOMAIN_ID", "204")
    workspace = Path(__file__).resolve().parents[5]
    artifacts = workspace / "artifacts/d5-guidance-timing-20261006"
    artifacts.mkdir(parents=True, exist_ok=True)
    evidence_path = Path(
        tempfile.mkdtemp(prefix="receiver-chain-", dir=artifacts)
    )
    report = {
        "stages": [],
        "commands": [],
        "feedback": [],
        "guidance": [],
        "exits": {},
    }
    started = time.monotonic()
    rclpy.init()
    peer = rclpy.create_node("precision_receiver_chain_peer")
    state = UAVState(
        connected=True,
        pose_valid=True,
        attitude_valid=True,
        velocity_valid=True,
        flight_mode=2,
    )
    state.header.frame_id = "odom"
    processes, logs = {}, []
    handle = terminal = None
    markers = []
    phase = ""
    stage = "setup"

    def record_stage(name):
        nonlocal stage
        stage = name
        report["stages"].append(
            {"name": name, "elapsed_s": time.monotonic() - started}
        )
        print("receiver_chain_stage " + name, flush=True)

    def mode(request, response):
        report.setdefault("mode_requests", []).append(request.flight_mode)
        state.flight_mode = request.flight_mode
        response.success = True
        return response

    def arm(request, response):
        report.setdefault("arm_requests", []).append(request.arm)
        state.armed = request.arm
        state.position_z = 1.0 if request.arm else 0.0
        response.success = True
        return response

    peer.create_service(SetFlightMode, "/set_flight_mode", mode)
    peer.create_service(ArmMotors, "/arm_motors", arm)
    states = peer.create_publisher(UAVState, "/uav_state", 10)
    targets = peer.create_publisher(LandingTarget, "/landing_target", 1)
    blocker = peer.create_publisher(Float64, "/timing/block", 1)

    def command(message):
        report["commands"].append(
            {
                "elapsed_s": time.monotonic() - started,
                "stage": stage,
                "z": message.position_z,
                "measured_z": state.position_z,
                "phase": phase,
            }
        )

    def guidance(message):
        report["guidance"].append(
            {
                "elapsed_s": time.monotonic() - started,
                "valid": message.valid,
                "reason": message.reason,
                "source_ns": message.source_header.stamp.sec * 1000000000
                + message.source_header.stamp.nanosec,
            }
        )

    def feedback(event):
        nonlocal phase
        phase = event.feedback.phase
        report["feedback"].append(
            {
                "elapsed_s": time.monotonic() - started,
                "phase": phase,
                "target_valid": event.feedback.target_valid,
                "height": event.feedback.height_above_target_m,
            }
        )

    peer.create_subscription(UAVCommand, "/uav_command", command, 10)
    peer.create_subscription(
        LandingGuidanceTarget, "/landing/guidance_target", guidance, 10
    )
    peer.create_subscription(
        String, "/timing/block_state", lambda m: markers.append(m.data), 10
    )
    takeoff = ActionClient(peer, Takeoff, "/takeoff")
    precision = ActionClient(peer, PrecisionLand, "/precision_land")
    ownership = peer.create_client(
        GetActionOwnership, "/precision_landing/ownership"
    )
    capabilities = peer.create_client(
        GetCapabilities, "/platform/precision_landing/capabilities"
    )

    def start(name, command_line):
        log = (evidence_path / (name + ".log")).open("w")
        logs.append(log)
        processes[name] = subprocess.Popen(
            command_line, stdout=log, stderr=subprocess.STDOUT
        )

    params = {
        "precision_enabled": "true",
        "precision_tag_id": "7",
        "precision_tag_size_m": "0.2",
        "precision_horizontal_speed": "0.2",
        "precision_descent_speed": "0.1",
        "precision_align_tolerance": "0.1",
        "precision_handoff_height": "0.3",
        "precision_descent_floor_height": "0.2",
        "precision_max_height": "3.0",
        "precision_max_radius": "2.0",
        "precision_plane_z": "0.0",
        "precision_target_max_age": "0.3",
        "precision_lost_timeout": "2.0",
        "precision_acquire_timeout": "2.0",
        "precision_settle_observations": "5",
    }
    flight = [
        get_package_prefix("easyfly_flight_control")
        + "/lib/easyfly_flight_control/flight_control_node",
        "--ros-args",
        "-r",
        "__node:=receiver_chain_flight",
    ]
    for name, value in params.items():
        flight.extend(["-p", name + ":=" + value])
    root = math.sqrt(0.5)
    observation = [
        sys.executable,
        str(
            workspace
            / "src/execution/e3_control/easyfly_precision_landing/test/timing_queue_fixture.py"
        ),
        "--ros-args",
        "-r",
        "__node:=receiver_chain_observation",
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
        "-p",
        "diagnostics:=true",
    ]

    def pump(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            assert all(
                p.poll() is None for p in processes.values()
            ), "owned node exited"
            state.header.stamp = peer.get_clock().now().to_msg()
            states.publish(state)
            rclpy.spin_once(peer, timeout_sec=0.01)

    def until(predicate, budget=3.0):
        end = time.monotonic() + budget
        while not predicate() and time.monotonic() < end:
            pump(0.01)
        assert predicate(), "stage deadline: " + stage

    def wait(future, budget=4.0):
        until(future.done, budget)
        return future.result()

    def raw_frame():
        message = LandingTarget(
            tag_id=7,
            tag_size_m=0.2,
            valid=True,
            optical_depth_m=state.position_z,
            reprojection_error_px=0.2,
        )
        message.header.frame_id = "camera_down_optical_frame"
        message.header.stamp = peer.get_clock().now().to_msg()
        message.pose.position.z = state.position_z
        message.pose.orientation.w = 1.0
        source = (
            message.header.stamp.sec * 1000000000
            + message.header.stamp.nanosec
        )
        targets.publish(message)
        until(
            lambda: any(
                m["valid"] and m["source_ns"] == source
                for m in report["guidance"]
            ),
            0.2,
        )
        pump(0.045)
        return source

    try:
        start("observation", observation)
        start("flight", flight)
        until(
            lambda: takeoff.server_is_ready()
            and precision.server_is_ready()
            and ownership.service_is_ready()
            and capabilities.service_is_ready()
            and states.get_subscription_count() >= 2
            and targets.get_subscription_count() > 0
            and blocker.get_subscription_count() > 0,
            8.0,
        )
        pump(1.0)
        assert wait(
            capabilities.call_async(GetCapabilities.Request())
        ).implemented == [True]
        record_stage("takeoff_fake_feedback")
        takeoff_handle = wait(
            takeoff.send_goal_async(
                Takeoff.Goal(target_altitude=1.0, climb_speed=0.3)
            )
        )
        assert takeoff_handle.accepted
        assert wait(takeoff_handle.get_result_async(), 6.0).status == 4
        raw_frame()
        handle = wait(
            precision.send_goal_async(
                PrecisionLand.Goal(tag_id=7, timeout=15.0),
                feedback_callback=feedback,
            )
        )
        assert handle.accepted
        terminal = handle.get_result_async()
        report["goal_uuid"] = bytes(handle.goal_id.uuid).hex()
        record_stage("initial_five_frames")
        for _ in range(5):
            raw_frame()
        until(lambda: phase == "descend", 0.3)
        assert min(m["z"] for m in report["commands"][-5:]) < 1.0
        record_stage("observation_block_and_reset")
        blocker.publish(Float64(data=0.6))
        until(lambda: "started" in markers)
        until(lambda: phase == "lost_hold", 0.8)
        before = len(report["commands"])
        pump(0.06)
        held = report["commands"][before:]
        assert held and all(abs(m["z"] - 1.0) < 1e-6 for m in held)
        report["first_loss_hold"] = next(
            m
            for m in report["commands"]
            if m["stage"] == "observation_block_and_reset"
            and abs(m["z"] - 1.0) < 1e-6
        )
        state.position_z = (
            0.97  # explicit feedback perturbation, no dynamics claim
        )
        pump(0.12)
        assert all(
            abs(m["z"] - 1.0) < 1e-6 for m in report["commands"][before:]
        )
        until(lambda: "finished" in markers)
        until(
            lambda: any(
                m["reason"] == "receiver_processing_gap"
                for m in report["guidance"]
            ),
            0.4,
        )
        state.position_z = 1.0
        until(
            lambda: targets.get_subscription_count() > 0
            and states.get_subscription_count() >= 2,
            0.4,
        )
        record_stage("reacquire_one_to_four")
        for _ in range(4):
            raw_frame()
            until(lambda: phase == "reacquire_hold", 0.1)
            assert (
                phase == "reacquire_hold"
            ), "fewer than five new source frames descended"
            assert abs(report["commands"][-1]["z"] - 1.0) < 1e-6
        record_stage("fifth_frame_reacquired_not_yet_aligned")
        raw_frame()
        until(lambda: phase == "align", 0.2)
        assert abs(report["commands"][-1]["z"] - 1.0) < 1e-6
        record_stage("five_new_alignment_frames")
        for index in range(5):
            raw_frame()
            if index < 4:
                assert phase == "align"
                assert abs(report["commands"][-1]["z"] - 1.0) < 1e-6
        until(lambda: phase == "descend", 0.2)
        until(lambda: report["commands"][-1]["z"] < 1.0, 0.2)
        record_stage("sustained_loss_terminal")
        value = wait(terminal, 3.0)
        assert value.status == 6 and not value.result.success
        report["terminal"] = {
            "status": value.status,
            "success": value.result.success,
            "message": value.result.message,
        }
        request = GetActionOwnership.Request(goal_id=report["goal_uuid"])

        def released():
            response = wait(ownership.call_async(request))
            assert response.goal_id == request.goal_id
            report["ownership_goal_id"] = response.goal_id
            return response.state == GetActionOwnership.Response.RELEASED

        until(released)
        report["ownership"] = "RELEASED"
        assert report.get("mode_requests", []) == [3]
        assert report.get("arm_requests", []) == [True]
    except Exception as error:
        report["error"] = repr(error)
        raise
    finally:
        if handle is not None and terminal is not None and not terminal.done():
            try:
                wait(handle.cancel_goal_async())
                wait(terminal, 4.0)
            except Exception as error:
                report["cleanup_cancel_error"] = repr(error)
        for name, process in processes.items():
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=4.0)
            except subprocess.TimeoutExpired:
                report["forced_exit"] = name
                process.kill()
                process.wait(timeout=3.0)
            report["exits"][name] = process.returncode
        for log in logs:
            log.close()
        (evidence_path / "evidence.json").write_text(
            json.dumps(report, indent=2)
        )
        print("receiver_chain_evidence " + str(evidence_path), flush=True)
        for client in (takeoff, precision):
            client.destroy()
        peer.destroy_node()
        rclpy.shutdown()
        assert all(code == 0 for code in report["exits"].values()), report[
            "exits"
        ]
