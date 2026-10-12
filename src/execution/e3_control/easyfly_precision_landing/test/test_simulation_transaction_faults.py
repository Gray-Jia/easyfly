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

"""Explicit transaction gates with synthetic peers, not SITL or flight-state evidence."""

import json
import time

from easyfly_msgs.srv import ArmMotors, GetCapabilities, SetFlightMode
from easyfly_precision_landing.simulation import (
    FLIGHT_PROXY_FAULT_SCENARIOS, OWNED_BRIDGE_FAULT_SCENARIOS, parse_arguments,
)
from easyfly_precision_landing.simulation_transaction_faults import (
    CANCEL_TRANSACTION_SCENARIOS, UPSTREAM_ARM_SCENARIOS, TRANSACTION_SCENARIO_TYPES,
    available_bridge_snapshot,
)
from mavros_msgs.srv import CommandBool, SetMode
import pytest
import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup


@pytest.mark.parametrize('name', TRANSACTION_SCENARIO_TYPES)
@pytest.mark.parametrize('extra', [[], ['--mission'], ['--prepare-only']])
def test_transaction_faults_require_explicit_direct_action(name, extra):
    """Never infer flight authority or broaden the formal mission/prepare path."""
    with pytest.raises(SystemExit):
        parse_arguments(['--directory', '/not-created', '--px4-dir', '/not-read',
                         '--use-bundled-dds-profile', '--scenario', name, *extra])


@pytest.mark.parametrize('name', TRANSACTION_SCENARIO_TYPES)
def test_transaction_owner_and_terminal_are_layer_specific(name):
    """Upstream uncertainty cannot be mislabelled an independently faulted bridge."""
    args = parse_arguments(['--directory', '/not-created', '--px4-dir', '/not-read',
                            '--use-bundled-dds-profile', '--direct-action', '--scenario', name])
    kind = TRANSACTION_SCENARIO_TYPES[args.scenario]
    assert kind.action_name == '/takeoff'
    assert kind.terminal_status == (5 if name in CANCEL_TRANSACTION_SCENARIOS else 6)
    assert kind.owns_bridge == (name in CANCEL_TRANSACTION_SCENARIOS)
    assert (name in FLIGHT_PROXY_FAULT_SCENARIOS) == (name in UPSTREAM_ARM_SCENARIOS)
    assert (name in OWNED_BRIDGE_FAULT_SCENARIOS) == (name in CANCEL_TRANSACTION_SCENARIOS)


@pytest.mark.parametrize('bad', [
    'none', 'missing', 'shape', 'faulted', 'not_ready', 'old_clock', 'late_query',
    'wrong_clock', 'no_context', 'no_mode_peer', 'no_arm_peer', 'bad_json',
])
def test_bridge_health_requires_independent_live_query(bad):
    """An upstream timeout is not permission to infer a second bridge fault."""
    response = GetCapabilities.Response()
    response.header.frame_id, response.header.stamp.sec = 'odom', 10
    response.names = ['flight_command_transport']
    response.implemented, response.ready = [True], [True]
    detail = dict(reason='command_transport_available', command_fault=False, ready=True,
                  context_ok=True, clock_ns=10000000000,
                  mode_service_ready=True, arming_service_ready=True)
    if bad == 'faulted':
        detail['command_fault'] = True
    elif bad == 'not_ready':
        detail['ready'] = False
    elif bad == 'wrong_clock':
        detail['clock_ns'] = 1
    elif bad == 'no_context':
        detail['context_ok'] = False
    elif bad == 'no_mode_peer':
        detail['mode_service_ready'] = False
    elif bad == 'no_arm_peer':
        detail['arming_service_ready'] = False
    response.details = [json.dumps(detail)]
    clock, elapsed = 10000000000, .01
    if bad == 'old_clock':
        clock += 1100000000
    elif bad == 'late_query':
        elapsed = .31
    elif bad == 'shape':
        response.ready = [False]
    elif bad == 'bad_json':
        response.details = ['not JSON']
    elif bad == 'missing':
        response = None
    if bad == 'none':
        assert not available_bridge_snapshot(response, clock, elapsed)['command_fault']
    else:
        with pytest.raises(RuntimeError):
            available_bridge_snapshot(response, clock, elapsed)


@pytest.mark.parametrize('name', [
    'cancel-bridge-mode-late', 'cancel-bridge-arm-late', 'upstream-arm-late',
])
@pytest.mark.parametrize('release', [True, False, None])
@pytest.mark.parametrize('success', [True, False])
def test_actual_typed_reply_is_preserved_and_no_command_sent_after_cleanup(name, release, success):
    """Use real ROS deliveries with synthetic service peers, never FCU or cancellation proof."""
    rclpy.init()
    node = rclpy.create_node('transaction_reply_proxy_peer')
    group, calls = ReentrantCallbackGroup(), []
    upstream = name in UPSTREAM_ARM_SCENARIOS
    mode_case = '-mode-' in name

    def typed_mode(request, response):
        calls.append(('mode', request.custom_mode if not upstream else request.flight_mode))
        if upstream:
            response.success, response.message = success, 'mode=OFFBOARD'
        else:
            response.mode_sent = success
        return response

    def typed_arm(request, response):
        calls.append(('arm', request.arm if upstream else request.value))
        response.success = success
        if upstream:
            response.message = 'armed' if success else 'explicitly rejected'
        else:
            response.result = 0 if success else 2
        return response

    node.create_service(SetFlightMode if upstream else SetMode,
                        '/set_flight_mode' if upstream else '/mavros/set_mode',
                        typed_mode, callback_group=group)
    node.create_service(ArmMotors if upstream else CommandBool,
                        '/arm_motors' if upstream else '/mavros/cmd/arming',
                        typed_arm, callback_group=group)
    probe = TRANSACTION_SCENARIO_TYPES[name](
        name, node, {'precision_feedback': []}, {}, {}, time.monotonic())
    kind = ArmMotors if upstream else SetMode if mode_case else CommandBool
    topic = ('/d5_test/arm_motors' if upstream else
             '/d5_test/mavros/set_mode' if mode_case else '/d5_test/mavros/cmd/arming')
    request = (ArmMotors.Request(arm=True) if upstream else
               SetMode.Request(custom_mode='OFFBOARD') if mode_case else
               CommandBool.Request(value=True))
    client = node.create_client(kind, topic, callback_group=group)

    def pump():
        rclpy.spin_once(node, timeout_sec=.01)

    def wait(predicate):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            pump()
            if predicate():
                return
        assert predicate(), 'transaction proxy deadline'

    try:
        wait(lambda: client.service_is_ready() and probe.real_arm.service_is_ready()
             and probe.real_mode.service_is_ready())
        pending = client.call_async(request)
        wait(lambda: probe.pending_since is not None)
        assert not pending.done() and not calls
        entries = probe.mode_calls if mode_case else probe.arm_calls
        if release is None:
            probe.drain(pump)
            wait(pending.done)
            assert not calls
            assert not (pending.result().mode_sent if mode_case else pending.result().success)
            return
        probe.admission_gate.set_result(True)  # Synthetic gate, not flight authorization.
        wait(lambda: 'upstream_reply_steady' in entries[0])
        assert len(calls) == 1 and not pending.done()
        if release:
            probe.reply_gate.set_result(True)
        else:
            probe.drain(pump)
            assert 'returned_steady' not in entries[0]
        wait(pending.done)
        response = pending.result()
        assert (response.mode_sent if mode_case else response.success) == success
        if upstream:
            assert response.message == ('armed' if success else 'explicitly rejected')
        elif not mode_case:
            assert response.result == (0 if success else 2)
        assert len(calls) == 1
    finally:
        probe.drain(pump)
        probe.destroy()
        assert rclpy.get_global_executor().shutdown(timeout_sec=1)
        node.destroy_node()
        rclpy.shutdown()
