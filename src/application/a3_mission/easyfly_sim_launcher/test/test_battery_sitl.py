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

"""Check declared battery diagnostic tasks without launching a simulator or flying."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

SOURCE = Path(__file__).parents[1] / 'scripts/battery_sitl.py'
SPEC = importlib.util.spec_from_file_location('battery_sitl', SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.mark.parametrize('failure', [False, True])
def test_declared_cycles_stop_at_first_failure(tmp_path, failure):
    """An unexpected failure cannot append another takeoff or compensating Land."""
    probe = object.__new__(MODULE.BatteryProbe)
    probe.args = SimpleNamespace(cycles=3)
    probe.directory, probe.report = tmp_path, {}
    probe.node = SimpleNamespace(create_subscription=Mock())
    probe.start = Mock()
    probe.send = Mock(return_value='owned')
    probe.finish = Mock(side_effect=RuntimeError('battery_invalid_timeout') if failure else None)
    probe.wait = Mock()
    probe.state = Mock(return_value={'armed': False, 'connected': True})
    if failure:
        with pytest.raises(RuntimeError, match='battery_invalid_timeout'):
            probe.run()
        assert probe.report['cycles_completed'] == 0
        assert probe.send.call_count == 1
        assert not (tmp_path / 'battery-cycle-2.yaml').exists()
        assert 'final_disarmed_state' not in probe.report
    else:
        probe.run()
        assert probe.report['cycles_completed'] == 3
        assert probe.send.call_count == 3
        assert probe.report['final_disarmed_state']['armed'] is False
    probe.start.assert_called_once()
    contents = (tmp_path / 'battery-cycle-1.yaml').read_text()
    assert 'failure_policy: abort' in contents
    # Predeclared positive step, not failure compensation.
    assert contents.count('type: land') == 1
    assert 'duration: 20' in contents
