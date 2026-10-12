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

"""Ordinary Land fixture policy, not aircraft or true cancellation evidence."""

from types import SimpleNamespace

from easyfly_precision_landing.simulation import (
    FLIGHT_PROXY_FAULT_SCENARIOS, OWNED_BRIDGE_FAULT_SCENARIOS, parse_arguments,
)
from easyfly_precision_landing.simulation_land_cancel_faults import (
    LAND_CANCEL_FAULT_SCENARIOS, CancelLandModeScenario,
)
import pytest


@pytest.mark.parametrize('name', LAND_CANCEL_FAULT_SCENARIOS)
@pytest.mark.parametrize('extra', [[], ['--mission'], ['--prepare-only']])
def test_ordinary_land_requires_explicit_direct_action(name, extra):
    """Never submit a Land or infer authority from a named negative scenario alone."""
    with pytest.raises(SystemExit):
        parse_arguments(['--directory', '/not-created', '--px4-dir', '/not-read',
                         '--use-bundled-dds-profile', '--scenario', name, *extra])


@pytest.mark.parametrize('name', LAND_CANCEL_FAULT_SCENARIOS)
def test_ordinary_land_is_original_goal_not_precision_parent_or_child(name):
    """Keep terminal type and fault layer tied to the actual Land transaction."""
    args = parse_arguments(['--directory', '/not-created', '--px4-dir', '/not-read',
                            '--use-bundled-dds-profile', '--direct-action', '--scenario', name])
    assert args.scenario == name and name in FLIGHT_PROXY_FAULT_SCENARIOS
    assert name not in OWNED_BRIDGE_FAULT_SCENARIOS
    assert CancelLandModeScenario.action_name == '/land'
    assert CancelLandModeScenario.terminal_status == 6
    assert CancelLandModeScenario.parent_message_prefix == 'command_result_unknown:'


@pytest.mark.parametrize('code,goals', [(1, []), (0, []), (0, ['goal']), (1, ['goal'])])
def test_unknown_mode_requires_cancel_rejection_not_fake_cancel_ack(code, goals):
    """Only explicit rejection with no accepted Goal passes ordinary Land audit."""
    scenario = object.__new__(CancelLandModeScenario)
    scenario.report = {'scenario': {'pending_cancel_snapshot': True}}
    scenario.cancel = SimpleNamespace(
        done=lambda: True, result=lambda: SimpleNamespace(return_code=code, goals_canceling=goals))

    def wait(predicate, seconds):
        return predicate()

    if code == 1 and not goals:
        scenario.before_terminal_audit(wait)
        assert scenario.report['scenario']['cancel_response']['return_code'] == 1
    else:
        with pytest.raises(RuntimeError, match='incorrectly accepted'):
            scenario.before_terminal_audit(wait)
