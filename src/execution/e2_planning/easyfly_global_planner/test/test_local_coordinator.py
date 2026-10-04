"""Coordinator with real ROS mock flight/planner: ordering, routes, failures."""
import os
import signal
import subprocess
import time
import unittest

import rclpy
from rclpy.action import ActionClient, ActionServer, CancelResponse
from rclpy.qos import QoSProfile, DurabilityPolicy
from easyfly_msgs.action import FollowTrajectory, NavigateTo
from easyfly_msgs.msg import UAVState, NavigationSession
from easyfly_msgs.srv import SetNavigationSession, StopNavigation
from nav_msgs.msg import OccupancyGrid


class LocalCoordinatorTest(unittest.TestCase):
    def run_scenario(self, strategy, scenario):
        rclpy.init()
        node = rclpy.create_node('local_coordinator_mock')
        events, handles, start_times = [], {}, {}
        position = [0.0, 0.0, 1.0]
        goals = []
        blocked = False
        reset_stamp = False
        flight_mode = 3
        active = ''
        fault_pub = node.create_publisher(NavigationSession, '/planning/navigation_fault',
                                          QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        stops = node.create_client(StopNavigation, '/navigate/_stop_owned')

        async def execute(handle):
            session = handle.request.navigation_session_id
            handles[session] = handle
            goals.append(handle.request)
            events.append(('accept', session))
            complete = rclpy.task.Future()

            def poll():
                nonlocal blocked, reset_stamp, flight_mode
                if complete.done():
                    return
                if handle.is_cancel_requested:
                    complete.set_result(False)
                elif session in start_times:
                    age = time.monotonic() - start_times[session]
                    if scenario == 'dynamic' and len(goals) == 1 and age > 0.1:
                        blocked = True
                    if scenario == 'invalid' and age > 0.1:
                        reset_stamp = True
                    if scenario == 'emergency' and age > 0.1:
                        fault_pub.publish(NavigationSession(session_id=session, active=False))
                    if scenario in ('rtl', 'land') and age > 0.1:
                        flight_mode = 6 if scenario == 'rtl' else 7
                    if scenario == 'streamlost' and age > 0.1:
                        complete.set_result(False)
                    if scenario not in ('dynamic', 'invalid', 'cancel', 'owned', 'emergency',
                                        'rtl', 'land', 'streamlost') or len(goals) > 1:
                        if age > 0.15:
                            position[:] = [handle.request.target_x, handle.request.target_y, handle.request.target_z]
                            complete.set_result(True)

            timer = node.create_timer(0.02, poll)
            reached = await complete
            node.destroy_timer(timer)
            result = FollowTrajectory.Result()
            result.success = reached
            result.message = 'trajectory stream lost' if scenario == 'streamlost' else 'arrived' if reached else 'canceled'
            if handle.is_cancel_requested:
                handle.canceled()
            elif scenario == 'streamlost':
                handle.abort()
            else:
                handle.succeed()
            events.append(('terminal', session))
            return result

        def session(request, response):
            nonlocal active
            events.append(('start' if request.active else 'stop', request.session_id))
            if request.active:
                self.assertIn(request.session_id, handles)  # Follow accepted before planner start.
                self.assertEqual(active, '')  # Previous STOP was acknowledged.
                active = request.session_id
                start_times[active] = time.monotonic()
                fault_pub.publish(NavigationSession(session_id='old-session', active=False))
                response.success = scenario != 'reject'
            else:
                active = ''
                response.success = True
            return response

        flight = ActionServer(node, FollowTrajectory, '/follow_trajectory', execute,
                              cancel_callback=lambda _: CancelResponse.ACCEPT)
        planner = node.create_service(SetNavigationSession, '/planning/navigation_session', session)
        state_pub = node.create_publisher(UAVState, '/uav_state', 10)
        map_pub = node.create_publisher(OccupancyGrid, '/occupancy_grid', 10)

        def publish():
            stamp = node.get_clock().now().to_msg()
            state = UAVState()
            state.header.stamp, state.header.frame_id = stamp, 'odom'
            state.connected = state.pose_valid = state.armed = True
            state.velocity_valid = True
            state.flight_mode = flight_mode
            state.position_x, state.position_y, state.position_z = position
            state_pub.publish(state)
            grid = OccupancyGrid()
            grid.header.frame_id = 'odom'
            if not reset_stamp:
                grid.header.stamp = stamp
            grid.info.resolution = 0.2
            grid.info.width = grid.info.height = 60
            grid.info.origin.position.x = grid.info.origin.position.y = -4.0
            grid.info.origin.orientation.w = 1.0
            grid.data = [0] * 3600
            # A static wall requires a detour, but remains bounded and reachable.
            if scenario == 'static':
                for row in range(15, 26):
                    grid.data[row * 60 + 30] = 100
            if blocked:
                for row in range(18, 23):
                    grid.data[row * 60 + 26] = 100
            map_pub.publish(grid)

        timer = node.create_timer(0.05, publish)
        process = subprocess.Popen(['ros2', 'run', 'easyfly_global_planner',
                                    'navigation_coordinator_node', '--ros-args',
                                    '-p', 'strategy:=' + strategy,
                                    '-p', 'local_goal_distance:=1.5',
                                    '-p', 'cancel_timeout:=0.8'], start_new_session=True)
        client = ActionClient(node, NavigateTo, '/navigate')

        def wait(future, seconds=10):
            end = time.monotonic() + seconds
            while not future.done() and time.monotonic() < end:
                rclpy.spin_once(node, timeout_sec=0.02)
            self.assertTrue(future.done(), (scenario, events))
            return future.result()

        try:
            self.assertTrue(client.wait_for_server(timeout_sec=10))
            goal = NavigateTo.Goal()
            goal.target_x, goal.target_z, goal.max_speed = 4.0, 1.0, 1.0
            handle = wait(client.send_goal_async(goal))
            self.assertTrue(handle.accepted)
            if scenario in ('cancel', 'owned'):
                end = time.monotonic() + 3
                while not active and time.monotonic() < end:
                    rclpy.spin_once(node, timeout_sec=0.02)
                self.assertTrue(active)
                if scenario == 'cancel':
                    wait(handle.cancel_goal_async())
                else:
                    request = StopNavigation.Request()
                    request.navigation_goal_id = 'wrong-old-goal'
                    self.assertFalse(wait(stops.call_async(request)).success)
                    request.navigation_goal_id = bytes(handle.goal_id.uuid).hex()
                    self.assertTrue(wait(stops.call_async(request)).success)
            result = wait(handle.get_result_async())
            expected = 5 if scenario == 'cancel' else 6 if scenario in (
                'reject', 'invalid', 'owned', 'emergency', 'rtl', 'land', 'streamlost') else 4
            self.assertEqual(result.status, expected, events)
            self.assertEqual(result.result.success, expected == 4)
            if scenario == 'emergency':
                self.assertEqual(result.result.message, 'planner_emergency_stop')
            if scenario == 'streamlost':
                self.assertEqual(result.result.message, 'trajectory stream lost')
            if scenario in ('rtl', 'land'):
                self.assertEqual(result.result.message, 'navigation input invalid or stale')
            self.assertEqual(active, '')
            self.assertTrue(goals)
            if scenario in ('static', 'dynamic'):
                self.assertGreater(len(goals), 1)
                self.assertTrue(any(abs(g.target_y) > 0.1 for g in goals))
            for i, g in enumerate(goals):
                self.assertLessEqual(len(g.navigation_session_id), 128)
                self.assertEqual(g.acceptance_radius, 0.1)
                if i:
                    sid = goals[i - 1].navigation_session_id
                    self.assertLess(events.index(('terminal', sid)), events.index(('accept', g.navigation_session_id)))
                    self.assertLess(events.index(('stop', sid)), events.index(('accept', g.navigation_session_id)))
        finally:
            os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            flight.destroy()
            node.destroy_service(planner)
            client.destroy()
            node.destroy_node()
            rclpy.shutdown()

    def test_ego(self):
        self.run_scenario('ego', 'clear')

    def test_static_combined(self):
        self.run_scenario('combined', 'static')

    def test_dynamic_combined(self):
        self.run_scenario('combined', 'dynamic')

    def test_invalid_map(self):
        self.run_scenario('combined', 'invalid')

    def test_planner_rejection(self):
        self.run_scenario('ego', 'reject')

    def test_cancel(self):
        self.run_scenario('ego', 'cancel')

    def test_owned_stop(self):
        self.run_scenario('ego', 'owned')

    def test_emergency_event_is_owned(self):
        self.run_scenario('ego', 'emergency')

    def test_external_rtl(self):
        self.run_scenario('ego', 'rtl')

    def test_external_land(self):
        self.run_scenario('ego', 'land')

    def test_downstream_stream_failure(self):
        self.run_scenario('ego', 'streamlost')


if __name__ == '__main__':
    unittest.main()
