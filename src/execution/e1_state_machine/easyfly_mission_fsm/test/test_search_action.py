"""Actual search server and SDK with a mock unified navigator and timed telemetry."""
import math
import os
import signal
import subprocess
import tempfile
import threading
import time
import unittest
import rclpy
from rclpy.action import ActionClient, ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from easyfly_msgs.action import NavigateTo, SearchArea
from easyfly_msgs.msg import UAVState, Target3D, Target3DArray
from easyfly_msgs.srv import GetActionOwnership


class SearchActionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rclpy.init()
        cls.node = rclpy.create_node('d3_search_mock')
        cls.group = ReentrantCallbackGroup()
        cls.position = (0., 0., 1.5)
        cls.behavior, cls.calls, cls.cancel_count, cls.hold_after = 'success', [], 0, 100
        cls.old_state, cls.flight_mode, cls.cancel_delay = False, 3, .02
        cls.ownership = {}
        def query(request, response):
            response.goal_id = request.goal_id
            release = cls.ownership.get(request.goal_id)
            response.state = 0 if release is None else 2 if time.monotonic() >= release else 1
            return response
        cls.ownership_service = cls.node.create_service(GetActionOwnership, '/navigation/ownership', query)
        cls.pub = cls.node.create_publisher(UAVState, '/uav_state', 10)
        cls.target_pub = cls.node.create_publisher(Target3DArray, '/target_positions', 10)

        def telemetry():
            state = UAVState(connected=True, pose_valid=True, velocity_valid=True,
                             armed=True, flight_mode=cls.flight_mode)
            state.header.frame_id = 'odom'
            state.header.stamp = cls.node.get_clock().now().to_msg()
            if cls.old_state:
                state.header.stamp.sec -= 10
            state.position_x, state.position_y, state.position_z = cls.position
            cls.pub.publish(state)
            array = Target3DArray()
            array.header.frame_id = 'odom'
            array.header.stamp = cls.node.get_clock().now().to_msg()
            for identity in (12, 12, 13, -1, 99):
                target = Target3D(track_id=identity, position_valid=True, confidence=.9)
                target.header.frame_id = 'odom'
                target.header.stamp = cls.node.get_clock().now().to_msg()
                target.position_x = 100. if identity == 99 else 0.
                array.targets.append(target)
            stale = Target3D(track_id=40, position_valid=True, confidence=.9)
            stale.header.frame_id = 'odom'
            stale.header.stamp = cls.node.get_clock().now().to_msg()
            stale.header.stamp.sec -= 10
            array.targets.append(stale)
            cls.target_pub.publish(array)

        cls.timer = cls.node.create_timer(.02, telemetry)

        def goal(_):
            if cls.behavior == 'late':
                time.sleep(.35)
            return GoalResponse.REJECT if cls.behavior == 'reject' else GoalResponse.ACCEPT

        def cancel(_):
            cls.cancel_count += 1
            return CancelResponse.ACCEPT

        def execute(handle):
            identity = bytes(handle.goal_id.uuid).hex()
            cls.ownership[identity] = float('inf')
            cls.calls.append(handle.request)
            behavior = cls.behavior
            if behavior == 'managed_drain':
                cls.ownership[identity] = time.monotonic() + .6
                handle.abort()
                return NavigateTo.Result(success=False, message='public_failure_still_owned')
            hold = behavior in ('hold', 'late') or len(cls.calls) > cls.hold_after
            while hold and not handle.is_cancel_requested and cls.process.poll() is None:
                time.sleep(.01)
            if handle.is_cancel_requested:
                time.sleep(cls.cancel_delay)
                cls.ownership[identity] = time.monotonic()
                handle.canceled()
                return NavigateTo.Result(success=False, message='real_cancel_terminal')
            if behavior == 'false_success':
                cls.ownership[identity] = time.monotonic()
                handle.succeed()
                return NavigateTo.Result(success=False, message='false_success')
            cls.position = (handle.request.target_x, handle.request.target_y, handle.request.target_z)
            time.sleep(.16 if behavior == 'late_success' else .06)
            cls.ownership[identity] = time.monotonic()
            handle.succeed()
            return NavigateTo.Result(success=True, message='mock_arrival')

        cls.backend = ActionServer(cls.node, NavigateTo, '/navigate', execute,
                                   goal_callback=goal, cancel_callback=cancel,
                                   callback_group=cls.group)
        cls.client = ActionClient(cls.node, SearchArea, '/search_area')
        cls.executor = MultiThreadedExecutor(num_threads=6)
        cls.executor.add_node(cls.node)
        cls.thread = threading.Thread(target=cls.executor.spin)
        cls.thread.start()
        cls.log = tempfile.TemporaryFile(mode='w+')
        cls.process = subprocess.Popen(['ros2', 'run', 'easyfly_mission_fsm', 'search_area_node',
                                       '--ros-args', '-p', 'segment_timeout:=0.15',
                                       '-p', 'cancel_timeout:=0.1', '-p', 'total_timeout:=5.0'],
                                      stdout=cls.log, stderr=cls.log, start_new_session=True)
        if not cls.client.wait_for_server(timeout_sec=8):
            cls.log.seek(0)
            raise RuntimeError(cls.log.read())
        time.sleep(.3)

    @classmethod
    def tearDownClass(cls):
        if cls.process.poll() is None:
            os.killpg(cls.process.pid, signal.SIGINT)
        try:
            cls.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(cls.process.pid, signal.SIGKILL)
            cls.process.wait(timeout=5)
        cls.executor.shutdown(timeout_sec=5)
        cls.thread.join(timeout=5)
        cls.backend.destroy()
        cls.client.destroy()
        cls.node.destroy_service(cls.ownership_service)
        cls.node.destroy_node()
        rclpy.shutdown()
        cls.log.close()

    def setUp(self):
        type(self).behavior = 'success'
        type(self).old_state, type(self).flight_mode = False, 3
        type(self).hold_after, type(self).cancel_delay = 100, .02
        time.sleep(.25)
        self.calls.clear()
        self.feedback = []

    def wait(self, future, timeout=5):
        until = time.monotonic() + timeout
        while not future.done() and time.monotonic() < until:
            time.sleep(.005)
        self.assertTrue(future.done())
        return future.result()

    def send(self, **overrides):
        values = dict(center_x=0., center_y=0., area_width=4., area_height=3.,
                      search_altitude=1.5, search_pattern=1, search_speed=1.)
        values.update(overrides)
        return self.wait(self.client.send_goal_async(SearchArea.Goal(**values),
            feedback_callback=lambda f: self.feedback.append(f.feedback)))

    def test_complete_geometry_and_unique_fresh_target_ids(self):
        handle = self.send()
        self.assertTrue(handle.accepted)
        result = self.wait(handle.get_result_async())
        self.assertEqual(result.status, 4)
        self.assertTrue(result.result.success)
        self.assertEqual(len(self.calls), 4)
        self.assertEqual([g.target_x for g in self.calls], [-2., 2., 2., -2.])
        self.assertEqual(result.result.total_targets_found, 2)
        areas = [f.area_covered for f in self.feedback]
        self.assertTrue(areas)
        self.assertIn(0., areas)
        self.assertEqual(areas[-1], 12.)
        self.assertEqual(self.feedback[-1].progress, 1.)
        self.assertEqual(areas, sorted(areas))

    def test_invalid_modes_geometry_and_stale_state_do_not_navigate(self):
        for values in ({'search_pattern': 0}, {'search_pattern': 2}, {'center_x': 50.},
                       {'search_altitude': 3.}, {'area_width': math.nan}, {'search_speed': 0.}):
            self.assertFalse(self.send(**values).accepted)
        type(self).old_state = True
        time.sleep(.1)
        self.assertFalse(self.send().accepted)
        self.assertFalse(self.calls)

    def test_false_success_does_not_count_coverage(self):
        type(self).behavior = 'false_success'
        handle = self.send()
        result = self.wait(handle.get_result_async())
        self.assertEqual(result.status, 6)
        self.assertFalse(result.result.success)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.feedback[-1].area_covered, 0.)

    def test_partial_cancel_ack_is_not_terminal_or_new_admission(self):
        type(self).hold_after, type(self).cancel_delay = 2, .35
        handle = self.send()
        until = time.monotonic() + 3
        while len(self.calls) < 3 and time.monotonic() < until:
            time.sleep(.005)
        self.assertEqual(len(self.calls), 3)
        self.wait(handle.cancel_goal_async())
        result = self.wait(handle.get_result_async())
        self.assertEqual(result.status, 5)
        self.assertFalse(result.result.success)
        self.assertIn('unconfirmed', result.result.message)
        self.assertEqual(self.feedback[-1].area_covered, 6.)
        self.assertFalse(self.send().accepted)
        time.sleep(.4)

    def test_late_admission_is_canceled_and_slot_stays_locked(self):
        type(self).behavior = 'late'
        before = self.cancel_count
        handle = self.send()
        result = self.wait(handle.get_result_async())
        self.assertEqual(result.status, 6)
        self.assertIn('unconfirmed', result.result.message)
        self.assertFalse(self.send().accepted)
        time.sleep(.5)
        self.assertGreater(self.cancel_count, before)

    def test_takeover_cancels_owned_navigation(self):
        type(self).behavior = 'hold'
        handle = self.send()
        until = time.monotonic() + 2
        while not self.calls and time.monotonic() < until:
            time.sleep(.005)
        type(self).flight_mode = 6
        result = self.wait(handle.get_result_async())
        self.assertEqual(result.status, 6)
        self.assertIn('state_invalid_or_takeover', result.result.message)
        self.assertFalse(result.result.success)

    def test_public_navigation_failure_is_not_actual_ownership_release(self):
        type(self).behavior = 'managed_drain'
        handle = self.send()
        result = self.wait(handle.get_result_async())
        self.assertEqual(result.status, 6)
        self.assertIn('unconfirmed', result.result.message)
        self.assertFalse(self.send().accepted)
        time.sleep(.7)

    def test_late_success_does_not_count_area_or_start_next_segment(self):
        type(self).behavior = 'late_success'
        handle = self.send()
        result = self.wait(handle.get_result_async())
        self.assertEqual(result.status, 6)
        self.assertIn('navigation_segment_timeout', result.result.message)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.feedback[-1].area_covered, 0.)


if __name__ == '__main__':
    unittest.main()
