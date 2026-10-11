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

"""Validate fault probes independently of PX4; never claim synthetic peers are SITL."""

import json
import time

from easyfly_msgs.srv import ArmMotors, GetCapabilities, SetFlightMode
from easyfly_precision_landing.simulation import parse_arguments
from easyfly_precision_landing.simulation_faults import (
    FAULT_SCENARIOS, ModeFaultScenario, fault_snapshot,
)
import pytest
import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup


@pytest.mark.parametrize('name', FAULT_SCENARIOS)
@pytest.mark.parametrize('extra', [[], ['--mission'], ['--prepare-only']])
def test_reply_injection_requires_direct_action(name, extra):
    """Keep response faults off all implicit and formal mission launch paths."""
    with pytest.raises(SystemExit):
        parse_arguments(['--directory', '/not-created', '--px4-dir', '/not-read',
                         '--use-bundled-dds-profile', '--scenario', name, *extra])


@pytest.mark.parametrize('fault', [
    'none', 'missing', 'shape', 'not_faulted', 'wrong_reason', 'busy', 'precision_busy',
    'reserved', 'old_clock', 'old_source', 'old_receipt', 'late_query', 'nan_receipt',
    'bad_json', 'empty_state', 'bool_sequence',
])
def test_latch_requires_fresh_explicit_fault_and_released_action(fault):
    """A normal rejection, stale snapshot or another busy action cannot prove a latch."""
    response = GetCapabilities.Response()
    response.header.frame_id, response.header.stamp.sec = 'odom', 10
    response.names, response.implemented, response.ready = ['takeoff'], [True], [False]
    detail = dict(reason='command_uncertain', command_uncertain=True, ready=False,
                  state_received=True, state_sequence=3, state_source_ns=10000000000,
                  clock_ns=10000000000, receipt_age_s=.01, active=0,
                  action_reserved=False, precision_reserved=False)
    clock, elapsed = 10000000000, .01
    changes = {'not_faulted': ('command_uncertain', False), 'wrong_reason': ('reason', 'busy'),
               'busy': ('active', 2), 'precision_busy': ('precision_reserved', True),
               'reserved': ('action_reserved', True), 'old_source': ('state_source_ns', 1),
               'old_receipt': ('receipt_age_s', 1.),
               'nan_receipt': ('receipt_age_s', float('nan')),
               'empty_state': ('state_sequence', 0), 'bool_sequence': ('state_sequence', True)}
    if fault in changes:
        key, value = changes[fault]
        detail[key] = value
    if fault == 'old_clock':
        clock += 1100000000
    if fault == 'late_query':
        elapsed = .31
    response.details = [json.dumps(detail)]
    if fault == 'bad_json':
        response.details = ['[]']
    if fault == 'shape':
        response.ready = [True]
    if fault == 'missing':
        response = None
    if fault == 'none':
        assert fault_snapshot(response, clock, elapsed)['command_uncertain']
    else:
        with pytest.raises(RuntimeError):
            fault_snapshot(response, clock, elapsed)


@pytest.mark.parametrize('name,status,success', [
    ('unknown-mode-late', 4, True), ('unknown-mode-withheld', 5, False),
    ('unknown-mode-late', 6, True),
])
def test_fault_terminal_cannot_be_signed_as_landing_success(name, status, success):
    """Reject a wrong real terminal before attempting ownership or latch queries."""
    from types import SimpleNamespace as NS
    probe = ModeFaultScenario.__new__(ModeFaultScenario)
    probe.name = name
    with pytest.raises(RuntimeError, match='unexpected true terminal'):
        probe.accept_terminal(NS(status=status, result=NS(success=success)), None)


@pytest.mark.parametrize('fault', [
    'none', 'wrong_uuid', 'old_feedback', 'old_mode', 'missing_child', 'terminal_child',
    'no_output', 'no_platform', 'wrong_mode',
])
def test_forward_gate_requires_owned_fresh_handoff(monkeypatch, fault):
    """Do not forward the flight command using stale phases or missing real baselines."""
    from types import SimpleNamespace as NS
    import easyfly_precision_landing.simulation_faults as faults
    from rclpy.task import Future
    monkeypatch.setattr(faults.time, 'monotonic', lambda: 100.)
    probe = ModeFaultScenario.__new__(ModeFaultScenario)
    probe.pending_since, probe.injected, probe.started = 99.95, None, 0.
    probe.identity = 'a' * 32
    probe.node = NS(get_clock=lambda: NS(now=lambda: NS(nanoseconds=10000000000)))
    probe.report = {
        'precision_feedback': [dict(
            goal_uuid=probe.identity, phase='land_handoff', elapsed_s=99.95)],
        'scenario': {},
    }
    probe.latest = {
        '/uav_state': NS(header=NS(stamp=NS(sec=10, nanosec=0)), connected=True,
                         armed=True, pose_valid=True, flight_mode_name='OFFBOARD',
                         position_x=0., position_y=0., position_z=.55),
        '/flight_status': NS(header=NS(stamp=NS(sec=10, nanosec=0)), connected=True,
                             armed=True, valid=True, flight_mode_name='OFFBOARD',
                             receipt_age_s=.01)}
    probe.receipts = {topic: 99.95 for topic in probe.latest}
    probe.land_statuses = {'b' * 32: 2}
    probe.output_samples = [dict(topic='/mavros/setpoint_position/local', steady=t)
                            for t in (99.6, 99.9)]
    probe.commands = [dict(steady=t) for t in (99.6, 99.9)]
    probe.admission_gate = Future()
    if fault == 'wrong_uuid':
        probe.report['precision_feedback'][0]['goal_uuid'] = 'c' * 32
    elif fault == 'old_feedback':
        probe.report['precision_feedback'][0]['elapsed_s'] = 99.
    elif fault == 'old_mode':
        probe.latest['/flight_status'].header.stamp.sec = 8
    elif fault == 'missing_child':
        probe.land_statuses.clear()
    elif fault == 'terminal_child':
        probe.land_statuses['b' * 32] = 4
    elif fault == 'wrong_mode':
        probe.latest['/uav_state'].flight_mode_name = 'AUTO.LAND'
    elif fault in ('no_output', 'no_platform'):
        (probe.output_samples if fault == 'no_output' else probe.commands).clear()
        with pytest.raises(RuntimeError, match='baseline missing'):
            probe.tick()
        assert not probe.admission_gate.done()
        return
    probe.tick()
    assert probe.admission_gate.done() is (fault == 'none')
    assert (probe.injected is not None) is (fault == 'none')


@pytest.mark.parametrize('release', [True, False, None])
def test_real_ros_proxy_forwards_once_and_preserves_actual_reply(release):
    """Exercise asynchronous ROS delivery with synthetic services, no flight processes."""
    rclpy.init()
    node = rclpy.create_node('reply_proxy_peer')
    calls, arms = [], []

    def mode(request, response):
        calls.append(request.flight_mode)
        response.success, response.message = False, 'actual upstream explicit rejection'
        return response

    def arm(request, response):
        arms.append(request.arm)
        response.success, response.message = True, 'actual upstream armed'
        return response

    group = ReentrantCallbackGroup()
    node.create_service(SetFlightMode, '/set_flight_mode', mode, callback_group=group)
    node.create_service(ArmMotors, '/arm_motors', arm, callback_group=group)
    probe = ModeFaultScenario('unknown-mode-late', node, {}, {}, {}, time.monotonic())
    client = node.create_client(SetFlightMode, '/d5_test/set_flight_mode', callback_group=group)
    arm_client = node.create_client(ArmMotors, '/d5_test/arm_motors', callback_group=group)

    def wait(predicate):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.01)
            if predicate():
                return
        assert predicate(), 'ROS proxy deadline'

    try:
        wait(lambda: client.service_is_ready() and probe.real_mode.service_is_ready()
             and arm_client.service_is_ready() and probe.real_arm.service_is_ready())
        armed = arm_client.call_async(ArmMotors.Request(arm=True))
        wait(armed.done)
        assert armed.result().success and armed.result().message == 'actual upstream armed'
        first = client.call_async(SetFlightMode.Request(flight_mode=3))
        wait(first.done)
        assert not first.result().success
        assert first.result().message == 'actual upstream explicit rejection'
        held = client.call_async(SetFlightMode.Request(flight_mode=7))
        wait(lambda: probe.pending_since is not None)
        assert calls == [3] and not held.done()
        if release is None:
            probe.drain(lambda: rclpy.spin_once(node, timeout_sec=.01))
            wait(held.done)
            assert calls == [3]  # Closing before admission must not send a late flight command.
            assert not held.result().success
            assert held.result().message == 'fixture closed before forwarding'
            return
        probe.admission_gate.set_result(True)  # synthetic fixture, not injection evidence
        wait(lambda: 'upstream_reply_steady' in probe.mode_calls[-1])
        assert calls == [3, 7] and not held.done()
        assert 'returned_steady' not in probe.mode_calls[-1]
        assert probe.mode_calls[-1]['upstream_message'] == 'actual upstream explicit rejection'
        if release:
            probe.reply_gate.set_result(True)
        else:
            probe.drain(lambda: rclpy.spin_once(node, timeout_sec=.01))
            assert probe.report['scenario']['fixture_callbacks_drained']
            assert 'returned_steady' not in probe.mode_calls[-1]
            assert 'cleanup_returned_steady' in probe.mode_calls[-1]
        wait(held.done)
        assert not held.result().success
        assert held.result().message == 'actual upstream explicit rejection'
        assert calls == [3, 7] and arms == [True]
    finally:
        probe.drain(lambda: rclpy.spin_once(node, timeout_sec=.01))
        probe.destroy()
        assert rclpy.get_global_executor().shutdown(timeout_sec=1)
        node.destroy_node()
        rclpy.shutdown()
