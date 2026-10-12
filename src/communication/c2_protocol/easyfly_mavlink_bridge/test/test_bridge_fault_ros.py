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

"""Real bridge mode/arming timeouts with synthetic MAVROS peers, not an aircraft."""

import json
from pathlib import Path
import signal
import subprocess
import time

from ament_index_python.packages import get_package_prefix
from easyfly_msgs.msg import UAVCommand
from easyfly_msgs.srv import ArmMotors, GetCapabilities, SetFlightMode
from geometry_msgs.msg import PoseStamped, Twist
from mavros_msgs.msg import AttitudeTarget, PositionTarget
from mavros_msgs.srv import CommandBool, SetMode
import pytest
import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.parameter import Parameter
from rclpy.task import Future
from rosgraph_msgs.msg import Clock


@pytest.mark.parametrize('late', [True, False])
@pytest.mark.parametrize('transaction', ['mode', 'arm'])
def test_real_bridge_fault_query_and_direct_service_denials(tmp_path, late, transaction):
    """Prove bridge lock without any flight controller or physical MAVROS process."""
    rclpy.init()
    node = rclpy.create_node('bridge_fault_peer', parameter_overrides=[
        Parameter('use_sim_time', value=True)])
    group, gate = ReentrantCallbackGroup(), Future()
    calls, arms, outputs, snapshots = [], [], [], []
    completed = []

    async def mode(request, response):
        calls.append(request.custom_mode)
        if transaction == 'mode':
            await gate
        response.mode_sent = True
        completed.append(True)
        return response

    async def arm(request, response):
        arms.append(request.value)
        if transaction == 'arm':
            await gate
        response.success, response.result = True, 0
        if transaction == 'arm':
            completed.append(True)
        return response

    node.create_service(SetMode, '/mavros/set_mode', mode, callback_group=group)
    node.create_service(CommandBool, '/mavros/cmd/arming', arm, callback_group=group)
    clock = node.create_publisher(Clock, '/clock', 10)
    commands = node.create_publisher(UAVCommand, '/uav_command', 10)
    for kind, topic in (
        (PoseStamped, '/mavros/setpoint_position/local'),
        (Twist, '/mavros/setpoint_velocity/cmd_vel_unstamped'),
        (AttitudeTarget, '/mavros/setpoint_raw/attitude'),
        (PositionTarget, '/mavros/setpoint_raw/local'),
    ):
        node.create_subscription(kind, topic, outputs.append, 10)
    query = node.create_client(GetCapabilities, '/platform/mavlink_bridge/capabilities')
    mode_client = node.create_client(SetFlightMode, '/set_flight_mode')
    arm_client = node.create_client(ArmMotors, '/arm_motors')
    process, forced = None, False
    began = time.monotonic()
    stream = (tmp_path / 'bridge.log').open('w')

    def pump(predicate, budget=3):
        deadline = time.monotonic() + budget
        while time.monotonic() < deadline:
            stamp = int((10 + time.monotonic() - began) * 1e9)
            message = Clock()
            message.clock.sec, message.clock.nanosec = divmod(stamp, 1000000000)
            clock.publish(message)
            rclpy.spin_once(node, timeout_sec=.01)
            if predicate():
                return
        assert predicate(), 'bridge ROS fault deadline'

    def snapshot():
        future = query.call_async(GetCapabilities.Request())
        pump(future.done)
        response = future.result()
        assert response.names == ['flight_command_transport']
        detail = json.loads(response.details[0])
        snapshots.append(detail)
        return detail

    def deny():
        for client, request in (
            (mode_client, SetFlightMode.Request(flight_mode=3)),
            (arm_client, ArmMotors.Request(arm=True)),
            (arm_client, ArmMotors.Request(arm=False)),
        ):
            future = client.call_async(request)
            pump(future.done)
            response = future.result()
            assert not response.success
            assert response.message == (
                'command_result_unknown: bridge fault locked; '
                'inspect remote state before restart')
        assert calls == (['AUTO.LAND'] if transaction == 'mode' else [])
        assert arms == ([True] if transaction == 'arm' else [])

    try:
        executable = Path(get_package_prefix('easyfly_mavlink_bridge')) / (
            'lib/easyfly_mavlink_bridge/mavlink_bridge_node')
        process = subprocess.Popen([str(executable), '--ros-args', '-p', 'use_sim_time:=true'],
                                   stdout=stream, stderr=subprocess.STDOUT)
        pump(lambda: query.service_is_ready() and mode_client.service_is_ready()
             and arm_client.service_is_ready())
        pump(lambda: snapshot()['ready'] and snapshot()['clock_ns'] > 0)
        assert not snapshot()['command_fault']
        assert not calls and not arms and not outputs
        pump(lambda: commands.get_subscription_count() > 0)
        command = UAVCommand(control_mode=UAVCommand.POSITION, position_z=1.)
        command.header.frame_id = 'odom'
        command.header.stamp = node.get_clock().now().to_msg()
        commands.publish(command)
        pump(lambda: len(outputs) >= 2)  # Actual encoder output, synthetic commands only.
        future = (mode_client.call_async(SetFlightMode.Request(flight_mode=7))
                  if transaction == 'mode' else arm_client.call_async(ArmMotors.Request(arm=True)))
        pump(lambda: bool(calls if transaction == 'mode' else arms))
        # Query remains responsive while the service transaction is blocked.
        assert not snapshot()['command_fault'] and not future.done()
        pump(future.done, 7)
        response = future.result()
        assert not response.success
        assert response.message == ('command_result_unknown: MAVROS '
                                    + ('mode' if transaction == 'mode' else 'arming')
                                    + ' response unconfirmed')
        assert snapshot()['command_fault']
        assert snapshot()['mode_service_ready'] and snapshot()['arming_service_ready']
        deny()
        stopped = len(outputs)
        command.header.stamp = node.get_clock().now().to_msg()
        commands.publish(command)
        pump(lambda: time.monotonic() - began > 6.5, 3)
        assert len(outputs) == stopped
        if late:
            gate.set_result(True)
            pump(lambda: bool(completed))
            assert snapshot()['command_fault']
            deny()
            command.header.stamp = node.get_clock().now().to_msg()
            commands.publish(command)
            finished = time.monotonic()
            pump(lambda: time.monotonic() - finished >= .2)
            assert len(outputs) == stopped
        process.send_signal(signal.SIGINT)
        assert process.wait(timeout=5) == 0
    finally:
        if process is not None and process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                forced = True
        if not gate.done():
            gate.set_result(True)
        if (calls or arms) and not completed:
            pump(lambda: bool(completed))
        assert rclpy.get_global_executor().shutdown(timeout_sec=1)
        node.destroy_node()
        rclpy.shutdown()
        stream.close()
        (tmp_path / 'snapshots.json').write_text(json.dumps(snapshots, indent=2))
    assert not forced
    assert 'bridge fault latch set' in (tmp_path / 'bridge.log').read_text()
