# Copyright 2026 EasyFly Project
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

"""Real node exit during Land mode confirmation with a frozen positive clock."""

import os
from pathlib import Path
import signal
import subprocess
import time

from ament_index_python.packages import get_package_prefix
from easyfly_msgs.action import Land, Takeoff
from easyfly_msgs.msg import UAVState
from easyfly_msgs.srv import ArmMotors, SetFlightMode
import pytest
import rclpy
from rclpy.action import ActionClient
from rosgraph_msgs.msg import Clock


@pytest.mark.parametrize("stop_signal", [signal.SIGINT, signal.SIGTERM])
def test_exit_during_mode_confirmation(tmp_path, stop_signal):
    os.environ["ROS_DOMAIN_ID"] = "199"
    rclpy.init()
    node = rclpy.create_node("mode_wait_shutdown_peer")
    state = UAVState()
    state.connected = state.pose_valid = state.attitude_valid = True
    state.flight_mode = 3
    calls = []

    def arm(request, response):
        calls.append(("arm", request.arm))
        state.armed = request.arm
        state.position_z = 1.0 if request.arm else 0.0
        response.success = True
        return response

    def mode(request, response):
        calls.append(("mode", request.flight_mode))
        # Deliberately acknowledge the request without confirming AUTO.LAND.
        response.success = True
        return response

    node.create_service(ArmMotors, "/arm_motors", arm)
    node.create_service(SetFlightMode, "/set_flight_mode", mode)
    publisher = node.create_publisher(UAVState, "/uav_state", 10)
    clock_publisher = node.create_publisher(Clock, "/clock", 10)
    clock = Clock()
    clock.clock.sec = 10

    def publish():
        state.header.stamp = clock.clock
        publisher.publish(state)
        clock_publisher.publish(clock)

    node.create_timer(0.02, publish)
    takeoff = ActionClient(node, Takeoff, "/takeoff")
    land = ActionClient(node, Land, "/land")
    executable = Path(get_package_prefix("easyfly_flight_control")) / (
        "lib/easyfly_flight_control/flight_control_node"
    )
    process = None
    forced = False

    def until(predicate, timeout=8.0):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            assert process.poll() is None, "node exited before test signal"
            rclpy.spin_once(node, timeout_sec=0.02)
        assert predicate(), "fixture did not reach the required state"

    try:
        with (tmp_path / "node.log").open("w") as output:
            process = subprocess.Popen(
                [str(executable), "--ros-args", "-p", "use_sim_time:=true"],
                stdout=output,
                stderr=subprocess.STDOUT,
            )
            until(lambda: takeoff.server_is_ready() and land.server_is_ready())
            # Let the controller receive a ready, disarmed state before admission.
            start = time.monotonic()
            until(lambda: time.monotonic() - start > 0.15)
            goal = Takeoff.Goal()
            goal.target_altitude = 1.0
            goal.climb_speed = 0.5
            sent = takeoff.send_goal_async(goal)
            until(sent.done)
            assert sent.result().accepted
            result = sent.result().get_result_async()
            until(result.done)
            assert result.result().result.success
            sent_land = land.send_goal_async(Land.Goal())
            until(sent_land.done)
            assert sent_land.result().accepted
            until(lambda: ("mode", 7) in calls)
            # Ensure the service response was processed and the wait is active.
            start = time.monotonic()
            until(lambda: time.monotonic() - start > 0.15)
            calls_before = list(calls)
            start = time.monotonic()
            process.send_signal(stop_signal)
            returncode = process.wait(timeout=2.0)
            assert returncode == 0
            assert time.monotonic() - start < 2.0
            for _ in range(5):
                rclpy.spin_once(node, timeout_sec=0.02)
            assert calls == calls_before, "shutdown initiated another flight service"
    finally:
        if process is not None and process.poll() is None:
            forced = True
            process.kill()
            process.wait(timeout=2.0)
        node.destroy_node()
        rclpy.shutdown()
    assert not forced, "forced cleanup must not be counted as an exit PASS"
