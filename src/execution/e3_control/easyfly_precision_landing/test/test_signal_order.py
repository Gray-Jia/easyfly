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

"""Signals during executor work must not invalidate a native take's context."""

import os
import signal

from easyfly_precision_landing import node as observation
import pytest
import rclpy


@pytest.mark.parametrize('stop_signal', [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize('runtime_error', [False, True])
def test_signal_defers_context_shutdown_and_does_not_hide_errors(
    monkeypatch, stop_signal, runtime_error
):
    """Reproduce the precise lifecycle ordering, including a fatal-error counterexample."""
    calls = []
    prior = signal.getsignal(stop_signal)

    class Node:
        diagnostics = False

        def destroy_node(self):
            assert rclpy.ok()
            calls.append('destroy')

    class Executor:
        def add_node(self, _node):
            pass

        def spin_once(self, timeout_sec):
            assert timeout_sec <= .05
            calls.append('take_enter')
            os.kill(os.getpid(), stop_signal)
            # The native call must be allowed to finish with its context intact.
            assert rclpy.ok()
            calls.append('take_exit')
            if runtime_error:
                raise RuntimeError('native conversion failure is still fatal')

        def shutdown(self):
            assert rclpy.ok()
            calls.append('executor_stop')

    monkeypatch.setattr(observation, 'LandingTransform', Node)
    monkeypatch.setattr(observation, 'SingleThreadedExecutor', Executor)
    if runtime_error:
        with pytest.raises(RuntimeError, match='native conversion failure is still fatal'):
            observation.main(args=[])
    else:
        observation.main(args=[])
    assert calls == ['take_enter', 'take_exit', 'executor_stop', 'destroy']
    assert not rclpy.ok()
    assert signal.getsignal(stop_signal) == prior
