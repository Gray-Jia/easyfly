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

"""Real controller readiness with staged synthetic feedback, never SITL or arming."""

import json
from pathlib import Path
import signal
import subprocess
import time

from ament_index_python.packages import get_package_prefix
from easyfly_msgs.action import Takeoff
from easyfly_msgs.msg import UAVCommand, UAVState
from easyfly_msgs.srv import ArmMotors, GetCapabilities, SetFlightMode
import rclpy
from rclpy.action import ActionClient
from rclpy.parameter import Parameter
from rosgraph_msgs.msg import Clock


def test_internal_readiness_is_not_observer_or_endpoint_discovery(tmp_path):
    """Prove absent state/clock and frozen sources fail despite discovered actions."""
    rclpy.init()
    node = rclpy.create_node('takeoff_readiness_peer', parameter_overrides=[
        Parameter('use_sim_time', value=True)])
    clock_pub = node.create_publisher(Clock, '/clock', 10)
    states = node.create_publisher(UAVState, '/uav_state', 10)
    external_seen, commands, remote_calls, evidence = [], [], [], []
    node.create_subscription(UAVState, '/uav_state', external_seen.append, 10)
    node.create_subscription(UAVCommand, '/uav_command', commands.append, 10)

    def remote(request, response):
        remote_calls.append(str(request))
        response.success = False
        return response

    node.create_service(ArmMotors, '/arm_motors', remote)
    node.create_service(SetFlightMode, '/set_flight_mode', remote)
    capability = node.create_client(GetCapabilities, '/platform/flight_control/capabilities')
    action = ActionClient(node, Takeoff, '/takeoff')
    state = UAVState(connected=True, pose_valid=True, attitude_valid=True, flight_mode=2)
    state.header.frame_id, state.header.stamp.sec = 'odom', 10
    streams = {'clock': True, 'state': True, 'clock_sec': 10}
    process = None
    forced_cleanup = False
    stream = (tmp_path / 'node.log').open('w')

    def pump(predicate, budget=3):
        deadline = time.monotonic() + budget
        while time.monotonic() < deadline:
            assert process is None or process.poll() is None, 'controller exited'
            if streams['clock']:
                message = Clock()
                message.clock.sec = streams['clock_sec']
                clock_pub.publish(message)
            if streams['state']:
                states.publish(state)
            rclpy.spin_once(node, timeout_sec=.01)
            if predicate():
                return
        assert predicate(), 'readiness evidence deadline'

    def query():
        future = capability.call_async(GetCapabilities.Request())
        pump(future.done)
        response = future.result()
        assert response is not None and response.names == ['takeoff']
        snapshot = json.loads(response.details[0])
        evidence.append({'ready': list(response.ready), 'snapshot': snapshot})
        return response.ready[0], snapshot

    def reject():
        future = action.send_goal_async(Takeoff.Goal(target_altitude=1., climb_speed=.3))
        pump(future.done)
        assert not future.result().accepted

    try:
        # This observer really has fresh state and clock before the child exists.
        # Volatile feedback is deliberately paused while endpoints are discovered.
        pump(lambda: bool(external_seen) and node.get_clock().now().nanoseconds == 10000000000)
        streams['clock'] = streams['state'] = False
        executable = Path(get_package_prefix('easyfly_flight_control')) / (
            'lib/easyfly_flight_control/flight_control_node')
        process = subprocess.Popen([str(executable), '--ros-args', '-p', 'use_sim_time:=true'],
                                   stdout=stream, stderr=subprocess.STDOUT)
        pump(lambda: capability.service_is_ready() and action.server_is_ready())
        ready, snapshot = query()
        assert not ready and snapshot['reason'] == 'state_not_received'
        assert external_seen[-1].pose_valid
        reject()
        streams['state'] = True
        pump(lambda: states.get_subscription_count() >= 2)
        pump(lambda: query()[1]['state_received'])
        ready, snapshot = query()
        assert not ready and snapshot['reason'] == 'clock_not_initialized'
        reject()
        streams['clock'] = True
        pump(lambda: query()[0])
        for _ in range(3):
            assert query()[0]
        assert not commands and not remote_calls
        streams['clock_sec'] = 12  # state receives new callbacks but retains source=10s
        pump(lambda: node.get_clock().now().nanoseconds == 12000000000)
        pump(lambda: query()[1]['clock_ns'] == 12000000000)
        ready, snapshot = query()
        assert not ready and snapshot['reason'] == 'source_stale_or_future'
        reject()
        assert not commands and not remote_calls
    finally:
        if process is not None and process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                forced_cleanup = True
        stream.close()
        (tmp_path / 'evidence.json').write_text(json.dumps(evidence, indent=2))
        action.destroy()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    assert process is not None and process.returncode == 0
    assert not forced_cleanup, 'owned controller required forced cleanup'
    log = (tmp_path / 'node.log').read_text()
    assert 'Takeoff admission rejected goal_uuid=' in log
    for reason in ('state_not_received', 'clock_not_initialized', 'source_stale_or_future'):
        assert reason in log
