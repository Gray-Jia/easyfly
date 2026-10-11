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
    PrecisionScenario, exact_cancel, fresh_owned_state, held_commands,
    loss_hold_end, remaining_owned,
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
