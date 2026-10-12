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

"""Validate downstream reply gates without aircraft or manufactured flight observations."""

import json
import time

from easyfly_msgs.srv import GetCapabilities
from easyfly_precision_landing.simulation import parse_arguments
from easyfly_precision_landing.simulation_bridge_faults import (
    BRIDGE_FAULT_SCENARIOS, BridgeModeFaultScenario, bridge_fault_snapshot,
)
from mavros_msgs.srv import CommandBool, SetMode
import pytest
import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup


@pytest.mark.parametrize('name', BRIDGE_FAULT_SCENARIOS)
@pytest.mark.parametrize('extra', [[], ['--mission'], ['--prepare-only']])
def test_bridge_faults_require_explicit_direct_action(name, extra):
    """Reject implicit flight or injection on the formal mission path."""
    with pytest.raises(SystemExit):
        parse_arguments(['--directory', '/not-created', '--px4-dir', '/not-read',
                         '--use-bundled-dds-profile', '--scenario', name, *extra])


@pytest.mark.parametrize('fault', [
    'none', 'missing', 'wrong_name', 'not_faulted', 'wrong_reason', 'old_clock', 'late_query',
    'wrong_clock', 'no_context', 'no_mode_peer', 'no_arm_peer', 'bad_json', 'outer_only',
])
def test_bridge_latch_is_distinct_and_fresh(fault):
    """Do not substitute an outer flight latch or unavailable peer for the bridge fault."""
    response = GetCapabilities.Response()
    response.header.frame_id, response.header.stamp.sec = 'odom', 10
    response.names = ['flight_command_transport']
    response.implemented, response.ready = [True], [False]
    detail = dict(reason='command_fault_locked', command_fault=True, ready=False,
                  context_ok=True, clock_ns=10000000000,
                  mode_service_ready=True, arming_service_ready=True)
    changes = {'not_faulted': ('command_fault', False), 'wrong_reason': ('reason', 'unavailable'),
               'no_context': ('context_ok', False), 'no_mode_peer': ('mode_service_ready', False),
               'no_arm_peer': ('arming_service_ready', False), 'wrong_clock': ('clock_ns', 1)}
    if fault in changes:
        key, value = changes[fault]
        detail[key] = value
    if fault == 'outer_only':
        detail.pop('command_fault')
        detail['command_uncertain'] = True
    response.details = [json.dumps(detail)]
    clock, elapsed = 10000000000, .01
    if fault == 'old_clock':
        clock += 1100000000
    elif fault == 'late_query':
        elapsed = .31
    elif fault == 'wrong_name':
        response.names = ['takeoff']
    elif fault == 'bad_json':
        response.details = ['[]']
    elif fault == 'missing':
        response = None
    if fault == 'none':
        assert bridge_fault_snapshot(response, clock, elapsed)['command_fault']
    else:
        with pytest.raises(RuntimeError):
            bridge_fault_snapshot(response, clock, elapsed)


@pytest.mark.parametrize('release', [True, False, None])
def test_typed_mavros_proxy_preserves_reply_and_drains_without_late_commands(release):
    """Use real ROS async delivery with synthetic MAVROS services, never SITL proof."""
    rclpy.init()
    node = rclpy.create_node('bridge_reply_proxy_peer')
    calls, arms = [], []

    def mode(request, response):
        calls.append((request.base_mode, request.custom_mode))
        response.mode_sent = False
        return response

    def arm(request, response):
        arms.append(request.value)
        response.success, response.result = True, 0
        return response

    group = ReentrantCallbackGroup()
    node.create_service(SetMode, '/mavros/set_mode', mode, callback_group=group)
    node.create_service(CommandBool, '/mavros/cmd/arming', arm, callback_group=group)
    probe = BridgeModeFaultScenario('bridge-mode-late', node, {}, {}, {}, time.monotonic())
    client = node.create_client(SetMode, '/d5_test/mavros/set_mode', callback_group=group)
    arm_client = node.create_client(
        CommandBool, '/d5_test/mavros/cmd/arming', callback_group=group)

    def pump():
        rclpy.spin_once(node, timeout_sec=.01)

    def wait(predicate):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            pump()
            if predicate():
                return
        assert predicate(), 'typed MAVROS proxy deadline'

    try:
        wait(lambda: client.service_is_ready() and probe.real_mode.service_is_ready()
             and arm_client.service_is_ready() and probe.real_arm.service_is_ready())
        armed = arm_client.call_async(CommandBool.Request(value=True))
        wait(armed.done)
        assert armed.result().success and armed.result().result == 0
        first = client.call_async(SetMode.Request(custom_mode='OFFBOARD'))
        wait(first.done)
        assert not first.result().mode_sent
        held = client.call_async(SetMode.Request(custom_mode='AUTO.LAND'))
        wait(lambda: probe.pending_since is not None)
        assert calls == [(0, 'OFFBOARD')] and not held.done()
        if release is None:
            probe.drain(pump)
            wait(held.done)
            assert calls == [(0, 'OFFBOARD')] and not held.result().mode_sent
            return
        probe.admission_gate.set_result(True)  # Synthetic service test, not flight-stage evidence.
        wait(lambda: 'upstream_reply_steady' in probe.mode_calls[-1])
        assert calls == [(0, 'OFFBOARD'), (0, 'AUTO.LAND')] and not held.done()
        assert probe.mode_calls[-1]['upstream_success'] is False
        if release:
            probe.reply_gate.set_result(True)
        else:
            probe.drain(pump)
            assert 'returned_steady' not in probe.mode_calls[-1]
        wait(held.done)
        assert not held.result().mode_sent
        assert arms == [True]
    finally:
        probe.drain(pump)
        probe.destroy()
        assert rclpy.get_global_executor().shutdown(timeout_sec=1)
        node.destroy_node()
        rclpy.shutdown()
