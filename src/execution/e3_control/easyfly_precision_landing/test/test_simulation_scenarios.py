# Copyright 2026 EasyFly Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Guard diagnostic acceptance against wrong UUID, stale state and fabricated success."""

import os
from pathlib import Path
from types import SimpleNamespace as NS

from easyfly_precision_landing.simulation import parse_arguments
from easyfly_precision_landing.simulation_scenarios import (
    DOWNSTREAM_TOPICS, TAKEOVERS, PrecisionScenario, exact_cancel, fresh_owned_state,
    fresh_status_mode, held_commands,
    downstream_baseline, loss_hold_end, remaining_owned,
)
import pytest


@pytest.mark.parametrize('arguments', [[], ['--mission'], ['--prepare-only']])
def test_scenarios_require_explicit_direct_flight(arguments):
    """Reject injection configuration with no explicit direct-action authority."""
    with pytest.raises(SystemExit):
        parse_arguments(['--directory', '/not-created', '--px4-dir', '/not-read',
                         '--use-bundled-dds-profile', '--scenario', 'cancel-descent', *arguments])


@pytest.mark.parametrize('mode,age,receipt,armed,expected', [
    ('OFFBOARD', 0., .1, True, True), ('OFFBOARD', 1.1, .1, True, False),
    ('OFFBOARD', 0., .4, True, False), ('AUTO.LAND', 0., .1, True, False),
    ('OFFBOARD', 0., .1, False, False),
])
def test_injection_requires_fresh_owned_state(mode, age, receipt, armed, expected):
    """Do not treat a cached phase or disconnected aircraft as an injection gate."""
    state = NS(header=NS(stamp=NS(sec=10, nanosec=0)), connected=True,
               armed=armed, pose_valid=True, flight_mode_name=mode,
               position_x=0., position_y=0., position_z=1.)
    assert fresh_owned_state(state, 100 - receipt, int((10 + age) * 1e9),
                             100., 'OFFBOARD') is expected


def test_observer_metadata_does_not_enable_producer_diagnostics_or_motion():
    """Keep native metadata capture separate from the control-node trace flag."""
    args = parse_arguments(['--directory', '/not-created', '--px4-dir', '/not-read',
                            '--use-bundled-dds-profile', '--observer-rmw-diagnostics'])
    assert args.observer_rmw_diagnostics and not args.transform_diagnostics
    assert not args.mission and not args.direct_action
    assert not args.ingress_timing_diagnostics


def test_ingress_trace_does_not_enable_transform_diagnostics_or_motion():
    """The opt-in native ingress recorder grants no flight or controller tracing."""
    args = parse_arguments(['--directory', '/not-created', '--px4-dir', '/not-read',
                            '--use-bundled-dds-profile', '--ingress-timing-diagnostics'])
    assert args.ingress_timing_diagnostics and not args.transform_diagnostics
    assert not args.mission and not args.direct_action


@pytest.mark.parametrize('change', ['none', 'descend', 'drift', 'velocity', 'missing'])
def test_loss_hold_uses_real_fixed_command(change):
    """A lowering or drifting command cannot pass the lost-target hold check."""
    commands = [{'steady': .2, 'mode': 0, 'position': [1., 2., 1.]},
                {'steady': .3, 'mode': 0, 'position': [1., 2., 1.]}]
    if change == 'descend':
        commands[-1]['position'][2] -= .01
    elif change == 'drift':
        commands[-1]['position'][0] += .01
    elif change == 'velocity':
        commands[-1]['mode'] = 1
    elif change == 'missing':
        commands.pop()
    assert held_commands(commands, 0., .4) is (change == 'none')


@pytest.mark.parametrize('identity,code', [('a' * 32, 0), ('b' * 32, 0), ('a' * 32, 1)])
def test_cancel_ack_requires_exact_goal(identity, code):
    """A successful unrelated cancel must not prove our action stopped."""
    response = NS(return_code=code, goals_canceling=[
        NS(goal_id=NS(uuid=list(bytes.fromhex(identity))))])
    assert exact_cancel(response, 'a' * 32) is (identity == 'a' * 32 and code == 0)


@pytest.mark.parametrize('name,status,success', [
    ('cancel-descent', 4, True), ('cancel-handoff', 6, False),
    ('loss-persistent', 5, False), ('external-takeover', 4, True),
    ('loss-recover', 6, False),
    ('external-posctl-descent', 4, True), ('external-posctl-handoff', 5, False),
    ('external-rtl-descent', 4, False), ('external-rtl-handoff', 6, True),
])
def test_negative_terminal_cannot_be_signed_as_success(name, status, success):
    """Only the specified real action terminal may reach ownership verification."""
    scenario = PrecisionScenario.__new__(PrecisionScenario)
    scenario.name, scenario.injected = name, 1.
    with pytest.raises(RuntimeError, match='unexpected true terminal'):
        scenario.accept_terminal(NS(status=status, result=NS(success=success)), None)


def test_matching_terminal_without_injection_is_not_acceptance():
    """A run that missed its phase window cannot become a passing cancellation test."""
    scenario = PrecisionScenario.__new__(PrecisionScenario)
    scenario.name, scenario.injected = 'cancel-descent', None
    with pytest.raises(RuntimeError, match='before requested injection'):
        scenario.accept_terminal(NS(status=5, result=NS(success=False)), None)


def test_loss_hold_excludes_new_hover_after_real_failure():
    """A post-failure hold point is not evidence of movement during the lost phase."""
    feedback = [{'goal_uuid': 'a', 'phase': 'lost_hold', 'elapsed_s': .4},
                {'goal_uuid': 'a', 'phase': 'failed', 'elapsed_s': .5}]
    ended = loss_hold_end(feedback, 'a', 0., None)
    commands = [{'steady': .2, 'mode': 0, 'position': [0., 0., 1.]},
                {'steady': .3, 'mode': 0, 'position': [0., 0., 1.]},
                {'steady': .6, 'mode': 0, 'position': [0., 0., .99]}]
    assert held_commands(commands, 0., ended)
    assert not held_commands(commands, 0., 1.)
    with pytest.raises(RuntimeError, match='boundary evidence missing'):
        loss_hold_end(feedback, 'wrong', 0., None)


def test_residual_identity_guard_includes_zombie_and_rejects_reused_pid():
    """Validate exact lifetime, not mere executable existence."""
    pid = str(os.getpid())
    ticks = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    assert remaining_owned({pid: {'start_ticks': ticks}})
    assert not remaining_owned({pid: {'start_ticks': str(int(ticks) + 1)}})


@pytest.mark.parametrize('samples', [
    [], [{'topic': '/mavros/setpoint_raw/local', 'steady': 9.9}],
    [{'topic': '/mavros/setpoint_position/local', 'steady': 8.0}] * 2,
    [{'topic': '/mavros/setpoint_position/local', 'steady': 10.1}] * 2,
    [{'topic': '/mavros/setpoint_position/local', 'steady': 9.9}],
])
def test_empty_wrong_old_future_or_single_downstream_is_not_stop_evidence(samples):
    """Absence on an unused topic cannot establish that a working bridge stopped."""
    with pytest.raises(RuntimeError, match='baseline missing'):
        downstream_baseline(samples, 10.)


def test_downstream_baseline_records_actual_position_traffic():
    """Include the real position-mode output and retain all four topic counts."""
    samples = [{'topic': '/mavros/setpoint_position/local', 'steady': t}
               for t in (9.6, 9.9)]
    counts = downstream_baseline(samples, 10.)
    assert counts['/mavros/setpoint_position/local'] == 2
    assert len(counts) == 4 and sum(counts.values()) == 2


def test_probe_observes_each_real_bridge_output_with_typed_callback():
    """The normal position output must not be hidden by a raw-only subscription."""
    subscriptions = []

    def subscribe(kind, topic, callback, qos):
        subscriptions.append((kind, topic, callback, qos))
        return object()

    node = NS(create_subscription=subscribe, create_client=lambda *args: object())
    report = {}
    scenario = PrecisionScenario('external-takeover', node, report, {}, {}, 0.)
    for (kind, topic), observed in zip(DOWNSTREAM_TOPICS, subscriptions):
        assert observed[:2] == (kind, topic)
        observed[2](kind())
    assert [s['topic'] for s in scenario.output_samples] == [
        topic for _, topic in DOWNSTREAM_TOPICS]
    assert len(scenario.outputs) == 4
    assert report['scenario']['downstream_samples'] is scenario.output_samples


def test_downstream_capacity_exhaustion_cannot_prove_no_new_output():
    """Fail rather than signing stream silence after a full recorder stops storing."""
    scenario = PrecisionScenario.__new__(PrecisionScenario)
    scenario.outputs = [1.] * 10000
    with pytest.raises(RuntimeError, match='capacity exhausted'):
        scenario.downstream('/mavros/setpoint_position/local', None)


@pytest.mark.parametrize('name', list(TAKEOVERS))
def test_takeover_modes_are_explicit_and_need_direct_action(name):
    """No arbitrary mode strings or implicit flight/injection from the new entries."""
    arguments = ['--directory', '/not-created', '--px4-dir', '/not-read',
                 '--use-bundled-dds-profile', '--scenario', name]
    with pytest.raises(SystemExit):
        parse_arguments(arguments)
    assert parse_arguments([*arguments, '--direct-action']).scenario == name
    assert TAKEOVERS[name][0] in ('AUTO.LAND', 'POSCTL', 'AUTO.RTL')


@pytest.mark.parametrize('fault', [
    'none', 'old_source', 'old_observer', 'old_origin', 'nan_origin', 'disarmed',
    'invalid', 'disconnected', 'wrong_mode', 'bad_stamp',
])
def test_mode_confirmation_needs_independent_fresh_evidence(fault):
    """A sent request or new aggregate timestamp cannot renew old PX4 mode evidence."""
    status = NS(header=NS(stamp=NS(sec=10, nanosec=0)), valid=True,
                connected=True, armed=True, flight_mode_name='POSCTL', receipt_age_s=.1)
    receipt, ros_now = 99.9, 10000000000
    if fault == 'old_source':
        ros_now += 1100000000
    elif fault == 'old_observer':
        receipt = 99.6
    elif fault == 'old_origin':
        status.receipt_age_s = .95
    elif fault == 'nan_origin':
        status.receipt_age_s = float('nan')
    elif fault == 'disarmed':
        status.armed = False
    elif fault == 'invalid':
        status.valid = False
    elif fault == 'disconnected':
        status.connected = False
    elif fault == 'wrong_mode':
        status.flight_mode_name = 'OFFBOARD'
    elif fault == 'bad_stamp':
        status.header.stamp.nanosec = 1000000000
    assert fresh_status_mode(status, receipt, ros_now, 100., 'POSCTL') is (fault == 'none')


@pytest.fixture
def takeover_probe(monkeypatch):
    """Build inert probe peers; neither ROS processes nor real mode commands run."""
    import easyfly_precision_landing.simulation_scenarios as probes
    monkeypatch.setattr(probes.time, 'monotonic', lambda: 100.)

    def create(name):
        calls = []
        mode, phase, baseline = TAKEOVERS[name]
        response = NS(done=lambda: True, result=lambda: NS(mode_sent=True))
        client = NS(service_is_ready=lambda: True,
                    call_async=lambda request: calls.append(request) or response)
        node = NS(create_subscription=lambda *args: object(), create_client=lambda *args: client,
                  get_clock=lambda: NS(now=lambda: NS(nanoseconds=10000000000)))
        state = NS(header=NS(stamp=NS(sec=10, nanosec=0)), connected=True,
                   armed=True, pose_valid=True, flight_mode_name=baseline,
                   position_x=0., position_y=0., position_z=.55)
        status = NS(header=NS(stamp=NS(sec=9, nanosec=900000000)), valid=True,
                    connected=True, armed=True, flight_mode_name=baseline, receipt_age_s=.05)
        latest = {'/uav_state': state, '/flight_status': status}
        receipts = {topic: 99.95 for topic in latest}
        report = {'precision_feedback': [{'goal_uuid': 'a' * 32, 'phase': phase,
                                         'elapsed_s': 99.95}]}
        scenario = PrecisionScenario(name, node, report, latest, receipts, 0.)
        scenario.identity = 'a' * 32
        scenario.output_samples = [{'topic': '/mavros/setpoint_position/local', 'steady': t}
                                   for t in (99.6, 99.9)]
        if phase == 'land_handoff':
            scenario.land_statuses = {'b' * 32: 2}
        return scenario, calls, mode, baseline

    return create


@pytest.mark.parametrize('name', list(TAKEOVERS))
def test_probe_injects_requested_mode_once_at_exact_phase(takeover_probe, name):
    """Keep legacy AUTO.LAND and new modes stage-bound, with no command resend."""
    scenario, calls, mode, _ = takeover_probe(name)
    scenario.report['precision_feedback'][-1]['phase'] = 'align'
    scenario.tick()
    assert not calls
    scenario.report['precision_feedback'][-1]['phase'] = TAKEOVERS[name][1]
    scenario.tick()
    scenario.tick()
    assert len(calls) == 1 and calls[0].custom_mode == mode
    assert scenario.report['scenario']['trigger_phase'] == TAKEOVERS[name][1]
    assert scenario.confirmed is None  # mode_sent alone is not mode confirmation


@pytest.mark.parametrize('fault', [
    'wrong_uuid', 'stale_feedback', 'stale_mode', 'no_child', 'terminal_child', 'no_downstream',
])
def test_handoff_injection_cannot_use_wrong_or_missing_baseline(takeover_probe, fault):
    """Require owned fresh AUTO.LAND, an executing child, and recent actual traffic."""
    scenario, calls, _, _ = takeover_probe('external-posctl-handoff')
    if fault == 'wrong_uuid':
        scenario.report['precision_feedback'][0]['goal_uuid'] = 'c' * 32
    elif fault == 'stale_feedback':
        scenario.report['precision_feedback'][0]['elapsed_s'] = 99.
    elif fault == 'stale_mode':
        scenario.latest['/flight_status'].header.stamp.sec = 8
    elif fault == 'no_child':
        scenario.land_statuses.clear()
    elif fault == 'terminal_child':
        scenario.land_statuses['b' * 32] = 4
    else:
        scenario.output_samples.clear()
        with pytest.raises(RuntimeError, match='baseline missing'):
            scenario.tick()
        assert not calls
        return
    scenario.tick()
    assert not calls and scenario.injected is None


def test_takeover_confirmation_requires_advancing_source_and_both_readers(takeover_probe):
    """Cached/aggregate-only requested modes cannot confirm actual takeover."""
    scenario, _, mode, _ = takeover_probe('external-posctl-descent')
    scenario.tick()
    scenario.latest['/uav_state'].flight_mode_name = mode
    assert not scenario.confirm_takeover()
    status = scenario.latest['/flight_status']
    status.flight_mode_name = mode
    assert not scenario.confirm_takeover()  # original source has not advanced
    status.header.stamp.sec, status.header.stamp.nanosec = 10, 0
    assert scenario.confirm_takeover()
    assert scenario.report['scenario']['confirmed_mode_evidence']['mode'] == mode
    status.flight_mode_name = 'OFFBOARD'
    scenario.flight_status(status)  # a duplicate old source is not new reclamation evidence
    status.header.stamp.nanosec = 100000000
    with pytest.raises(RuntimeError, match='reclaimed OFFBOARD'):
        scenario.flight_status(status)
