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

"""Explicit cancellation fixture policy tests, not flight or cancellation evidence."""

from types import SimpleNamespace

from easyfly_precision_landing.simulation import (
    FLIGHT_PROXY_FAULT_SCENARIOS, OWNED_BRIDGE_FAULT_SCENARIOS, parse_arguments,
)
from easyfly_precision_landing.simulation_precision_cancel_faults import (
    CHILD_UNKNOWN_MESSAGE, PRECISION_CANCEL_FAULT_SCENARIOS, CancelPrecisionModeScenario,
)
import pytest


@pytest.mark.parametrize('name', PRECISION_CANCEL_FAULT_SCENARIOS)
@pytest.mark.parametrize('extra', [[], ['--mission'], ['--prepare-only']])
def test_precision_cancel_requires_explicit_direct_action(name, extra):
    """Never infer flight authority from a named failure scenario alone."""
    with pytest.raises(SystemExit):
        parse_arguments(['--directory', '/not-created', '--px4-dir', '/not-read',
                         '--use-bundled-dds-profile', '--scenario', name, *extra])


@pytest.mark.parametrize('name', PRECISION_CANCEL_FAULT_SCENARIOS)
def test_canceled_parent_is_not_mislabelled_as_known_child_cancel(name):
    """Public parent CANCELED differs from true child ABORTED/unknown."""
    args = parse_arguments(['--directory', '/not-created', '--px4-dir', '/not-read',
                            '--use-bundled-dds-profile', '--direct-action', '--scenario', name])
    assert args.scenario == name
    assert name in FLIGHT_PROXY_FAULT_SCENARIOS
    assert name not in OWNED_BRIDGE_FAULT_SCENARIOS
    assert CancelPrecisionModeScenario.terminal_status == 5
    assert CancelPrecisionModeScenario.parent_message_prefix == (
        'precision landing canceled; child Land drained')
    assert CancelPrecisionModeScenario.expected_child_message(None, None) == CHILD_UNKNOWN_MESSAGE


@pytest.mark.parametrize('bad', ['reply_not_seen', 'deadline', 'reply_released', 'child_terminal'])
def test_cancel_gate_cannot_bypass_original_live_transaction(bad):
    """Reject absent actual successful reply, expired request, or already drained child."""
    scenario = object.__new__(CancelPrecisionModeScenario)
    scenario.confirmed, scenario.cancel = 1.0, None
    scenario.mode_calls = [{'received_steady': float('inf'), 'upstream_success': True}]
    scenario.reply_gate = SimpleNamespace(done=lambda: False)
    scenario.land_statuses = {'one-child': 2}
    if bad == 'reply_not_seen':
        scenario.mode_calls[0]['upstream_success'] = False
    elif bad == 'deadline':
        scenario.mode_calls[0]['received_steady'] = 0.0
    elif bad == 'reply_released':
        scenario.reply_gate = SimpleNamespace(done=lambda: True)
    else:
        scenario.land_statuses['one-child'] = 6
    # Already injected/confirmed, so the base observer tick cannot send a Goal.
    scenario.injected = 1.0
    scenario.confirm_real_land = lambda: None
    with pytest.raises(RuntimeError, match='not inside actual pending'):
        scenario.tick()
