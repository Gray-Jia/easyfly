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

"""Actual gateway with a fake backend: admission is not recursive release."""

import signal
import subprocess
import threading
import time

from ament_index_python.packages import get_package_prefix
from easyfly_msgs.action import PrecisionLand
from easyfly_msgs.srv import (
    GetActionOwnership,
    GetCapabilities,
    TriggerLanding,
)
import pytest
import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor


@pytest.mark.parametrize("stop_signal", [signal.SIGINT, signal.SIGTERM])
def test_gateway_unknown_admission_and_recursive_lock(stop_signal):
    """Unknown/public-failed child keeps the compatibility entrance busy."""
    rclpy.init()
    node = rclpy.create_node("landing_gateway_fixture")
    group = ReentrantCallbackGroup()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    release = [False]
    wrong_uuid = [False]
    calls = []

    def goal(_request):
        time.sleep(0.2)
        return GoalResponse.ACCEPT

    def execute(handle):
        calls.append(bytes(handle.goal_id.uuid).hex())
        handle.abort()
        return PrecisionLand.Result(
            success=False, message="public_failure_child_owned"
        )

    server = ActionServer(
        node,
        PrecisionLand,
        "/precision_land",
        execute,
        goal_callback=goal,
        cancel_callback=lambda _: CancelResponse.ACCEPT,
        callback_group=group,
    )

    def ownership(request, response):
        response.goal_id = "f" * 32 if wrong_uuid[0] else request.goal_id
        response.state = 2 if release[0] else 1
        return response

    owner = node.create_service(
        GetActionOwnership,
        "/precision_landing/ownership",
        ownership,
        callback_group=group,
    )

    def capabilities(_request, response):
        response.header.stamp = node.get_clock().now().to_msg()
        response.names = ["precision_landing"]
        response.implemented = response.ready = [True]
        return response

    backend = node.create_service(
        GetCapabilities,
        "/platform/precision_landing/capabilities",
        capabilities,
        callback_group=group,
    )
    thread = threading.Thread(target=executor.spin)
    thread.start()
    binary = (
        get_package_prefix("easyfly_precision_landing")
        + "/lib/easyfly_precision_landing/landing_gateway_node"
    )
    process = subprocess.Popen(
        [
            binary,
            "--ros-args",
            "-p",
            "selected_tag_id:=7",
            "-p",
            "admission_timeout_s:=0.05",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    client = node.create_client(TriggerLanding, "/trigger_landing")
    cap = node.create_client(
        GetCapabilities, "/platform/landing_trigger/capabilities"
    )

    def call(endpoint, request):
        future = endpoint.call_async(request)
        deadline = time.monotonic() + 3
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert future.done()
        return future.result()

    def wait_ready(expected):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            value = call(cap, GetCapabilities.Request()).ready[0]
            if value == expected:
                return
            time.sleep(0.05)
        assert value == expected

    try:
        assert client.wait_for_service(timeout_sec=5)
        assert cap.wait_for_service(timeout_sec=3)
        wait_ready(True)
        assert not call(
            client, TriggerLanding.Request()
        ).accepted  # Finite zero XY is unsupported.
        assert not calls
        request = TriggerLanding.Request(
            landing_x=float("nan"), landing_y=float("nan")
        )
        answer = call(client, request)
        assert not answer.accepted and answer.message.startswith(
            "admission_pending:"
        )
        deadline = time.monotonic() + 3
        while not calls and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(calls) == 1
        time.sleep(0.2)
        assert call(client, request).message == "busy_or_tag_not_configured"
        wait_ready(False)
        wrong_uuid[0] = True
        release[0] = True
        time.sleep(0.4)
        assert call(client, request).message == "busy_or_tag_not_configured"
        wrong_uuid[0] = False
        wait_ready(True)
        process.send_signal(stop_signal)
        output, _ = process.communicate(timeout=2)
        assert process.returncode == 0, output
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
        executor.shutdown(timeout_sec=2)
        thread.join(timeout=2)
        server.destroy()
        node.destroy_service(owner)
        node.destroy_service(backend)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
