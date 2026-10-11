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

"""Shutdown after dynamic tracking, DDS reader turnover and valid clock reset recovery."""

import signal

import pytest
from test_shutdown_ros import run_active_mapping_shutdown


@pytest.mark.parametrize('workload', ['moving-readers', 'clock-reset'])
@pytest.mark.parametrize('stop_signal', [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize('capture', [False, True])
def test_dynamic_shutdown(tmp_path, workload, stop_signal, capture):
    """Keep safety bounds unchanged and require useful processing, not only input sends."""
    run_active_mapping_shutdown(tmp_path, 'running', stop_signal, capture, workload)
