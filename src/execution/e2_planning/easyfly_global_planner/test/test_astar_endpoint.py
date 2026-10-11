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

"""Check real A* node endpoint/result contracts with explicit mock flight actions."""

import os
import signal
import subprocess
import time
import unittest

from easyfly_msgs.action import GoToWaypoint, NavigateTo
from easyfly_msgs.msg import UAVState
from nav_msgs.msg import OccupancyGrid
import rclpy
from rclpy.action import ActionClient, ActionServer
from rclpy.qos import DurabilityPolicy, QoSProfile


class EndpointTest(unittest.TestCase):
    """Do not substitute mocked motion for the separately recorded real SITL."""

    def test_endpoint_same_cell_and_false_success(self):
        """Preserve exact xy/z, issue same-cell motion and reject false child success."""
        rclpy.init()
        node = rclpy.create_node('astar_endpoint_mock')
        received = []

        def execute(handle):
            received.append(handle.request)
            handle.succeed()
            return GoToWaypoint.Result(success=handle.request.target_x != 1.1)

        server = ActionServer(node, GoToWaypoint, '/goto_waypoint', execute)
        states = node.create_publisher(UAVState, '/uav_state', 10)
        maps = node.create_publisher(OccupancyGrid, '/occupancy_grid', QoSProfile(
            depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))

        def publish():
            state = UAVState()
            state.header.frame_id = 'odom'
            state.header.stamp = node.get_clock().now().to_msg()
            state.connected = state.armed = state.pose_valid = state.velocity_valid = True
            state.flight_mode = 3
            state.position_x = -0.042944148182869
            state.position_y = 0.006087067071348429
            state.position_z = 1.5
            states.publish(state)
            grid = OccupancyGrid()
            grid.header = state.header
            grid.info.width = grid.info.height = 50
            grid.info.resolution = 0.2
            grid.info.origin.position.x = grid.info.origin.position.y = -5.0
            grid.info.origin.orientation.w = 1.0
            grid.data = [0] * 2500
            maps.publish(grid)

        timer = node.create_timer(0.05, publish)
        client = ActionClient(node, NavigateTo, '/navigate_astar')
        process = subprocess.Popen([
            'ros2', 'run', 'easyfly_global_planner', 'global_planner_node'],
            start_new_session=True)

        def wait(future):
            deadline = time.monotonic() + 10
            while not future.done() and time.monotonic() < deadline:
                rclpy.spin_once(node, timeout_sec=0.02)
            self.assertTrue(future.done())
            return future.result()

        try:
            self.assertTrue(client.wait_for_server(timeout_sec=15))
            until = time.monotonic() + 0.5
            while time.monotonic() < until:
                rclpy.spin_once(node, timeout_sec=0.02)
            for x, y, z, status in (
                    (1.957055851817131, 0.006087067071348429, 1.5, 4),
                    (-0.01, 0.07, 1.9, 4),
                    (1.1, 0.33, 1.5, 6)):
                with self.subTest(x=x, y=y, z=z):
                    before = len(received)
                    goal = NavigateTo.Goal(target_x=x, target_y=y, target_z=z, max_speed=0.6)
                    handle = wait(client.send_goal_async(goal))
                    self.assertTrue(handle.accepted)
                    result = wait(handle.get_result_async())
                    self.assertEqual(result.status, status)
                    self.assertEqual(result.result.success, status == 4)
                    self.assertGreater(len(received), before)
                    self.assertEqual(received[-1].target_x, x)
                    self.assertEqual(received[-1].target_y, y)
                    self.assertEqual(received[-1].target_z, z)
                    self.assertLessEqual(received[-1].acceptance_radius, 0.1)
                    until = time.monotonic() + 0.2
                    while time.monotonic() < until:
                        rclpy.spin_once(node, timeout_sec=0.02)
        finally:
            # ros2 run does not forward this owner-only signal to its child.
            # This is our isolated two-process mock group, not the SITL launch.
            os.killpg(process.pid, signal.SIGINT)
            process.wait(timeout=10)
            node.destroy_timer(timer)
            server.destroy()
            client.destroy()
            node.destroy_node()
            rclpy.shutdown()


if __name__ == '__main__':
    unittest.main()
