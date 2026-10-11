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

"""Inject stop immediately before the actual Humble native message take."""

import os
import signal
import subprocess
import sys
import time

from easyfly_msgs.msg import UAVState
import pytest
import rclpy


CHILD = '''
import os
import signal
import sys
import rclpy
from easyfly_precision_landing import node as observation
stop_signal = int(sys.argv[1])
diagnostics = sys.argv[2] == 'true'
base = observation.DiagnosticExecutor if diagnostics else observation.SingleThreadedExecutor
class SignalAtTake(base):
    def _take_subscription(self, subscription):
        if subscription.topic_name != '/uav_state':
            return super()._take_subscription(subscription)
        os.kill(os.getpid(), stop_signal)
        assert rclpy.ok(), 'signal invalidated context before native take'
        message = super()._take_subscription(subscription)
        assert message is not None, 'test requires an actual typed sample'
        assert rclpy.ok(), 'context lost while completing native take'
        print('REAL_NATIVE_TAKE_COMPLETED_WITH_VALID_CONTEXT', flush=True)
        return message
if diagnostics:
    observation.DiagnosticExecutor = SignalAtTake
else:
    observation.SingleThreadedExecutor = SignalAtTake
observation.main(args=['--ros-args', '-p', 'diagnostics:=' + sys.argv[2]])
assert not rclpy.ok()
'''


@pytest.mark.parametrize('stop_signal', [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize('diagnostics', [False, True])
def test_stop_during_actual_typed_take(stop_signal, diagnostics, tmp_path):
    """Require native conversion success and clean exit, not mere exception suppression."""
    rclpy.init()
    fixture = rclpy.create_node('signal_take_fixture')
    publisher = fixture.create_publisher(UAVState, '/uav_state', 10)
    path = tmp_path / 'node.log'
    with path.open('w') as log:
        process = subprocess.Popen(
            [sys.executable, '-c', CHILD, str(int(stop_signal)), str(diagnostics).lower()],
            stdout=log, stderr=log, env={**os.environ, 'RCUTILS_LOGGING_USE_STDOUT': '1'})
        try:
            deadline = time.monotonic() + 6.
            while process.poll() is None and time.monotonic() < deadline:
                message = UAVState(connected=True, pose_valid=True)
                message.header.frame_id = 'odom'
                message.header.stamp = fixture.get_clock().now().to_msg()
                publisher.publish(message)
                rclpy.spin_once(fixture, timeout_sec=.02)
            assert process.poll() == 0, path.read_text()
            output = path.read_text()
            assert 'REAL_NATIVE_TAKE_COMPLETED_WITH_VALID_CONTEXT' in output
            assert 'Traceback' not in output
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=3.)
            fixture.destroy_node()
            rclpy.shutdown()
