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

"""Actual bridge exit with an unanswered MAVROS request and frozen clock."""

import os
from pathlib import Path
import signal
import subprocess
import time

from ament_index_python.packages import get_package_prefix
from easyfly_msgs.srv import SetFlightMode
from mavros_msgs.srv import SetMode
import pytest
import rclpy
from rclpy.task import Future
from rosgraph_msgs.msg import Clock


@pytest.mark.parametrize("stop_signal", [signal.SIGINT, signal.SIGTERM])
def test_pending_service_shutdown(tmp_path, stop_signal):
    os.environ["ROS_DOMAIN_ID"] = "195"
    rclpy.init()
    node = rclpy.create_node("bridge_shutdown_peer")
    gate = Future()
    calls = []
    finished = []

    async def mode(request, response):
        calls.append(request.custom_mode)
        await gate
        response.mode_sent = True
        finished.append(True)
        return response

    node.create_service(SetMode, "/mavros/set_mode", mode)
    publisher = node.create_publisher(Clock, "/clock", 10)
    clock = Clock()
    clock.clock.sec = 10
    node.create_timer(0.02, lambda: publisher.publish(clock))
    client = node.create_client(SetFlightMode, "/set_flight_mode")
    executable = Path(get_package_prefix("easyfly_mavlink_bridge")) / (
        "lib/easyfly_mavlink_bridge/mavlink_bridge_node"
    )
    process = None
    forced = False

    def until(predicate):
        deadline = time.monotonic() + 5.0
        while not predicate() and time.monotonic() < deadline:
            assert process.poll() is None, "bridge exited before signal"
            rclpy.spin_once(node, timeout_sec=0.01)
        assert predicate(), "fixture never entered the pending request"

    try:
        with (tmp_path / "bridge.log").open("w") as output:
            process = subprocess.Popen(
                [str(executable), "--ros-args", "-p", "use_sim_time:=true"],
                stdout=output,
                stderr=subprocess.STDOUT,
            )
            until(client.service_is_ready)
            pending = client.call_async(SetFlightMode.Request(flight_mode=3))
            until(lambda: bool(calls))
            assert not pending.done()
            start = time.monotonic()
            process.send_signal(stop_signal)
            assert process.wait(timeout=2.0) == 0
            assert time.monotonic() - start < 2.0
            assert calls == [
                "OFFBOARD"
            ], "shutdown initiated another MAVROS request"
    finally:
        if process is not None and process.poll() is None:
            forced = True
            process.kill()
            process.wait(timeout=2.0)
        gate.set_result(True)
        # Complete the suspended fake server callback before destroying its
        # borrowed service handle; this is fixture cleanup, not bridge PASS.
        deadline = time.monotonic() + 1.0
        while calls and not finished and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.01)
        node.destroy_node()
        rclpy.shutdown()
    assert not forced, "forced cleanup is not a PASS"
