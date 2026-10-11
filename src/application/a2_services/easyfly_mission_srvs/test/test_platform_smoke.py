# Copyright 2026 EasyFly Project
#
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

"""Installed service launch smoke: queries only, no motion backend started."""
import json
import os
import signal
import subprocess
import tempfile
import time
import unittest

import rclpy
from easyfly_msgs.srv import GetPerception, GetCapabilities, ManageMission
from std_srvs.srv import Trigger


class PlatformSmokeTest(unittest.TestCase):
    def test_installed_service_launch(self):
        rclpy.init()
        node = rclpy.create_node('platform_smoke')
        log = tempfile.TemporaryFile(mode='w+')
        process = subprocess.Popen(
            [
                'ros2',
                'launch',
                'easyfly_mission_srvs',
                'platform.launch.py',
                'use_sim_time:=false',
            ],
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        perception = node.create_client(
            GetPerception, '/platform/perception/query'
        )
        catalog = node.create_client(ManageMission, '/platform/mission/manage')
        capability = node.create_client(
            GetCapabilities, '/platform/mission/capabilities'
        )
        export = node.create_client(Trigger, '/platform/params/export')

        def call(client, request):
            self.assertTrue(client.wait_for_service(timeout_sec=10))
            future = client.call_async(request)
            until = time.monotonic() + 5
            while not future.done() and time.monotonic() < until:
                rclpy.spin_once(node, timeout_sec=0.01)
            self.assertTrue(future.done())
            return future.result()

        try:
            result = call(perception, GetPerception.Request(kind='targets'))
            self.assertEqual(result.status, result.NOT_READY)
            result = call(catalog, ManageMission.Request(operation='list'))
            self.assertTrue(result.success)
            self.assertIn('waypoint_demo.mission', result.missions)
            result = call(capability, GetCapabilities.Request())
            self.assertEqual(result.ready, [False, False, False])
            result = call(export, Trigger.Request())
            self.assertTrue(result.success)
            self.assertEqual(
                json.loads(result.message)['name'], 'navigation_dev'
            )
            self.assertIsNone(process.poll())
        except Exception:
            log.seek(0)
            print(log.read())
            raise
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            log.close()
            node.destroy_node()
            rclpy.shutdown()


if __name__ == '__main__':
    unittest.main()
