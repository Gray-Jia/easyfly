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

"""Test explicit arming gates with synthetic ROS peers, not physical arming evidence."""

import asyncio
import time
from types import SimpleNamespace

from easyfly_msgs.msg import FlightStatus, UAVState
from easyfly_precision_landing.simulation import parse_arguments
from easyfly_precision_landing.simulation_arm_faults import (
    BRIDGE_ARM_FAULT_SCENARIOS, BridgeArmFaultScenario, fresh_arm_evidence,
)
from mavros_msgs.srv import CommandBool, SetMode
import pytest
import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.task import Future


@pytest.mark.parametrize('name', BRIDGE_ARM_FAULT_SCENARIOS)
@pytest.mark.parametrize('extra', [[], ['--mission'], ['--prepare-only']])
def test_arming_faults_require_explicit_direct_action(name, extra):
    """Do not infer flight authority or inject on mission/prepare paths."""
    with pytest.raises(SystemExit):
        parse_arguments(['--directory', '/not-created', '--px4-dir', '/not-read',
                         '--use-bundled-dds-profile', '--scenario', name, *extra])


@pytest.mark.parametrize('name', BRIDGE_ARM_FAULT_SCENARIOS)
def test_explicit_arming_scenario_targets_takeoff(name):
    """Only explicit direct action selects the bounded Takeoff fixture."""
    args = parse_arguments(['--directory', '/not-created', '--px4-dir', '/not-read',
                            '--use-bundled-dds-profile', '--direct-action', '--scenario', name])
    assert args.scenario == name
    assert BridgeArmFaultScenario.action_name == '/takeoff'


@pytest.mark.parametrize('armed', [False, True])
@pytest.mark.parametrize('bad', [
    'none', 'no_state', 'no_status', 'no_clock', 'no_source', 'old_state', 'old_status',
    'future_state', 'old_receipt', 'old_origin', 'wrong_mode', 'unconfirmed_mode',
    'disagree', 'unconnected', 'invalid_pose', 'invalid_status', 'nan',
])
def test_arming_requires_independent_live_sources(armed, bad):
    """ACK-only, mismatched arming, stale or invalid sources cannot satisfy the gate."""
    state = UAVState(connected=True, pose_valid=True, attitude_valid=True,
                     armed=armed, flight_mode=3, flight_mode_name='OFFBOARD')
    status = FlightStatus(connected=True, valid=True, armed=armed, flight_mode_name='OFFBOARD')
    state.header.stamp.sec = status.header.stamp.sec = 10
    clock, now = 10000000000, 100.
    receipts = {'/uav_state': 99.9, '/flight_status': 99.9}
    if bad == 'no_state':
        state = None
    elif bad == 'no_status':
        status = None
    elif bad == 'no_clock':
        clock = 0
    elif bad == 'no_source':
        state.header.stamp.sec = 0
    elif bad == 'old_state':
        state.header.stamp.sec = 8
    elif bad == 'old_status':
        status.header.stamp.sec = 8
    elif bad == 'future_state':
        state.header.stamp.sec = 11
    elif bad == 'old_receipt':
        receipts['/uav_state'] = 99.6
    elif bad == 'old_origin':
        status.receipt_age_s = 1.
    elif bad == 'wrong_mode':
        state.flight_mode = 7
    elif bad == 'unconfirmed_mode':
        status.flight_mode_name = 'AUTO.LAND'
    elif bad == 'disagree':
        status.armed = not armed
    elif bad == 'unconnected':
        state.connected = False
    elif bad == 'invalid_pose':
        state.pose_valid = False
    elif bad == 'invalid_status':
        status.valid = False
    elif bad == 'nan':
        state.position_z = float('nan')
    assert fresh_arm_evidence(state, status, receipts, clock, now, armed) == (bad == 'none')


@pytest.mark.parametrize('bad', ['none', 'wrong_identity', 'not_executing', 'stale', 'armed'])
def test_send_gate_requires_owned_executing_ground_and_both_sources_advance(bad):
    """Exercise the real gate with explicitly synthetic samples; never send a command."""
    now = time.monotonic()
    state = UAVState(connected=True, pose_valid=True, attitude_valid=True,
                     flight_mode=3, flight_mode_name='OFFBOARD')
    status = FlightStatus(connected=True, valid=True, flight_mode_name='OFFBOARD')
    state.header.stamp.sec = status.header.stamp.sec = 10
    clock = SimpleNamespace(nanoseconds=10000000000)
    probe = BridgeArmFaultScenario.__new__(BridgeArmFaultScenario)
    probe.node = SimpleNamespace(get_clock=lambda: SimpleNamespace(now=lambda: clock))
    probe.identity, probe.takeoff_statuses = '1' * 32, {'1' * 32: 2}
    probe.pending_since, probe.injected, probe.confirmed = now - .1, None, None
    probe.latest = {'/uav_state': state, '/flight_status': status}
    probe.receipts = dict.fromkeys(probe.latest, now)
    probe.commands = [dict(steady=now - .1), dict(steady=now - .05)]
    probe.output_samples = [dict(topic='/mavros/setpoint_position/local', steady=now - .1)] * 2
    probe.report, probe.admission_gate = {'scenario': {}}, Future()
    if bad == 'wrong_identity':
        probe.takeoff_statuses = {'2' * 32: 2}
    elif bad == 'not_executing':
        probe.takeoff_statuses = {probe.identity: 1}
    elif bad == 'stale':
        probe.receipts['/flight_status'] = now - .4
    elif bad == 'armed':
        state.armed = status.armed = True
    probe.tick()
    if bad != 'none':
        assert probe.injected is None and not probe.admission_gate.done()
        return
    assert probe.admission_gate.done() and probe.injected is not None
    assert probe.confirmed is None
    state.armed = status.armed = True
    probe.tick()  # Matching arming flags alone do not advance the source barrier.
    assert probe.confirmed is None
    clock.nanoseconds += 1000000000
    state.header.stamp.sec = 11
    probe.tick()
    assert probe.confirmed is None  # Only UAVState has advanced.
    status.header.stamp.sec = 11
    probe.tick()
    assert probe.confirmed is not None
    assert probe.report['scenario']['confirmed_arm_evidence']['state_armed']


@pytest.mark.parametrize('release', [True, False, None])
@pytest.mark.parametrize('ack', [(True, 0), (False, 2)])
def test_arming_proxy_preserves_actual_ack_and_drains(release, ack):
    """Use real ROS typed proxy delivery; never call this a real FCU or SITL result."""
    rclpy.init()
    node = rclpy.create_node('arming_reply_proxy_peer')
    calls, modes = [], []

    def arm(request, response):
        calls.append(request.value)
        response.success, response.result = ack
        return response

    def mode(request, response):
        modes.append((request.base_mode, request.custom_mode))
        response.mode_sent = True
        return response

    group = ReentrantCallbackGroup()
    node.create_service(CommandBool, '/mavros/cmd/arming', arm, callback_group=group)
    node.create_service(SetMode, '/mavros/set_mode', mode, callback_group=group)
    probe = BridgeArmFaultScenario('bridge-arm-late', node, {'precision_feedback': []},
                                   {}, {}, time.monotonic())
    client = node.create_client(CommandBool, '/d5_test/mavros/cmd/arming', callback_group=group)

    def pump():
        rclpy.spin_once(node, timeout_sec=.01)

    def wait(predicate):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            pump()
            if predicate():
                return
        assert predicate(), 'arming proxy deadline'

    try:
        wait(lambda: client.service_is_ready() and probe.real_arm.service_is_ready())
        pending = client.call_async(CommandBool.Request(value=True))
        wait(lambda: probe.pending_since is not None)
        assert not pending.done() and not calls
        if release is None:
            probe.drain(pump)
            wait(pending.done)
            assert not calls and not pending.result().success
            assert pending.result().result == 4
            return
        probe.admission_gate.set_result(True)  # Component-only gate, not flight readiness.
        wait(lambda: 'upstream_reply_steady' in probe.arm_calls[0])
        assert calls == [True] and not pending.done()
        assert (probe.arm_calls[0]['success'], probe.arm_calls[0]['result']) == ack
        if release:
            probe.reply_gate.set_result(True)
        else:
            probe.drain(pump)
            assert 'returned_steady' not in probe.arm_calls[0]
        wait(pending.done)
        assert (pending.result().success, pending.result().result) == ack
        assert calls == [True] and not modes
        for request in (CommandBool.Request(value=True), CommandBool.Request(value=False)):
            with pytest.raises(RuntimeError, match='retry|compensating'):
                asyncio.run(probe.arm_request(request, CommandBool.Response()))
        assert calls == [True]
    finally:
        probe.drain(pump)
        probe.destroy()
        assert rclpy.get_global_executor().shutdown(timeout_sec=1)
        node.destroy_node()
        rclpy.shutdown()
