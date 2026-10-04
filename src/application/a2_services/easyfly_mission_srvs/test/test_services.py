"""Actual service facade, mock mission backend: ownership and immutable input."""
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest
import threading

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from easyfly_msgs.action import ExecuteMission
from easyfly_msgs.srv import ManageMission, GetCapabilities, GetActionOwnership


class MissionServiceTest(unittest.TestCase):
    def run_scenario(self, scenario):
        rclpy.init()
        node = rclpy.create_node('mission_service_backend')
        backend_node = rclpy.create_node('late_cancel_backend') if scenario == 'late_cancel_reject' else node
        handles, snapshots, events = [], [], []
        released, known, release_after = set(), set(), {}
        def query_ownership(request, response):
            response.goal_id = request.goal_id
            if request.goal_id in release_after and time.monotonic() >= release_after[request.goal_id]:
                released.add(request.goal_id)
            response.state = 2 if request.goal_id in released else 1 if request.goal_id in known else 0
            return response
        owner = node.create_service(GetActionOwnership, '/mission/ownership', query_ownership)
        directory = tempfile.TemporaryDirectory(prefix='easyfly-d2-catalog-')
        root = Path(directory.name)
        (root / 'valid.mission').write_text('type=hover\nwait=0.1\n')
        (root / 'invalid.mission').write_text('type=land\n---\ntype=search\n')
        (root / 'yaml.yaml').write_text('schema_version: 1\nsteps:\n- type: land\n')
        (root / 'escape.mission').symlink_to('/etc/passwd')
        (root / 'alias.txt').symlink_to(root / 'valid.mission')

        def accept(_request):
            if scenario == 'late':
                time.sleep(0.4)
            return GoalResponse.REJECT if scenario == 'reject' else GoalResponse.ACCEPT

        async def execute(handle):
            identity = bytes(handle.goal_id.uuid).hex()
            known.add(identity)
            handles.append(handle)
            path = Path(handle.request.mission_file)
            snapshots.append(path)
            self.assertNotEqual(path.parent, root)
            self.assertEqual(path.read_text(), 'type=hover\nwait=0.1\n')
            # A later catalog mutation must not alter the already accepted input.
            (root / 'valid.mission').write_text('type=land\n')
            self.assertEqual(path.read_text(), 'type=hover\nwait=0.1\n')
            complete = rclpy.task.Future()
            started = time.monotonic()

            def poll():
                if complete.done():
                    return
                feedback = ExecuteMission.Feedback()
                feedback.current_status.header.stamp = node.get_clock().now().to_msg()
                feedback.current_status.progress = 0.5
                handle.publish_feedback(feedback)
                if handle.is_cancel_requested:
                    if scenario == 'slowcancel' and time.monotonic() - started < 0.8:
                        return  # ACK arrived, but the backend is not terminal.
                    events.append('canceled')
                    complete.set_result(False)
                elif scenario in ('success', 'fail', 'managed_drain', 'late_cancel_reject') and time.monotonic() - started > 0.3:
                    complete.set_result(scenario == 'success')

            timer = backend_node.create_timer(0.02, poll)
            result = await complete
            backend_node.destroy_timer(timer)
            response = ExecuteMission.Result(success=result, message='backend result')
            if scenario in ('managed_drain', 'late_cancel_reject'):
                release_after[identity] = time.monotonic() + .6
            else:
                released.add(identity)
            if handle.is_cancel_requested:
                handle.canceled()
            elif result:
                handle.succeed()
            else:
                handle.abort()
            return response

        def cancellation(_):
            if scenario == 'late_cancel_reject':
                time.sleep(.5)
                return CancelResponse.REJECT
            return CancelResponse.ACCEPT
        backend = None if scenario == 'unavailable' else ActionServer(
            backend_node, ExecuteMission, '/execute_mission', execute, goal_callback=accept,
            cancel_callback=cancellation, callback_group=ReentrantCallbackGroup())
        backend_executor, backend_thread = None, None
        if backend_node != node:
            backend_executor = MultiThreadedExecutor(num_threads=3)
            backend_executor.add_node(backend_node)
            backend_thread = threading.Thread(target=backend_executor.spin)
            backend_thread.start()
        log = tempfile.TemporaryFile(mode='w+')
        process = subprocess.Popen(['ros2', 'run', 'easyfly_mission_srvs', 'mission_services',
                                    '--ros-args', '-p', 'mission_directory:=' + str(root),
                                    '-p', 'response_timeout:=0.15'], stdout=log, stderr=log,
                                   start_new_session=True)
        api = node.create_client(ManageMission, '/platform/mission/manage')
        cap = node.create_client(GetCapabilities, '/platform/mission/capabilities')

        def wait(future, seconds=5):
            until = time.monotonic() + seconds
            while not future.done() and time.monotonic() < until:
                rclpy.spin_once(node, timeout_sec=0.01)
                self.assertIsNone(process.poll())
            self.assertTrue(future.done())
            return future.result()

        def call(operation, name='', execution=''):
            return wait(api.call_async(ManageMission.Request(operation=operation, mission_name=name,
                                                            execution_id=execution)))

        try:
            self.assertTrue(api.wait_for_service(timeout_sec=10))
            # Let backend discovery settle before checking unavailable/ready.
            until = time.monotonic() + 0.2
            while time.monotonic() < until:
                rclpy.spin_once(node, timeout_sec=0.01)
            result = call('list')
            self.assertTrue(result.success)
            self.assertIn('valid.mission', result.missions)
            self.assertNotIn('escape.mission', result.missions)
            self.assertNotIn('alias.txt', result.missions)
            self.assertTrue(call('validate', 'valid.mission').success)
            for name in ('invalid.mission', 'yaml.yaml', '../valid.mission', 'escape.mission', 'alias.txt'):
                self.assertFalse(call('validate', name).success)
            self.assertFalse(call('unsupported').success)
            self.assertFalse(call('cancel', execution='old-unknown-id').success)
            response = wait(cap.call_async(GetCapabilities.Request()))
            self.assertEqual(response.implemented, [True, True, True])
            result = call('start', 'valid.mission')
            if scenario == 'unavailable':
                self.assertFalse(result.success)
                self.assertEqual(result.status, 'unsupported')
                return
            if scenario == 'reject':
                self.assertFalse(result.success)
                self.assertEqual(result.status, 'rejected')
                self.assertFalse(handles)
                return
            self.assertTrue(result.execution_id)
            execution = result.execution_id
            if scenario in ('managed_drain', 'late_cancel_reject'):
                if scenario == 'late_cancel_reject':
                    call('cancel', execution=execution)
                until = time.monotonic() + 3
                current = call('query', execution=execution)
                while current.status != 'failed' and time.monotonic() < until:
                    current = call('query', execution=execution)
                self.assertEqual(current.status, 'failed')
                self.assertTrue(current.execution_pending)
                self.assertTrue(snapshots[0].exists())
                self.assertEqual(call('start', 'valid.mission').status, 'busy')
                while current.execution_pending and time.monotonic() < until:
                    current = call('query', execution=execution)
                self.assertFalse(current.execution_pending)
                self.assertEqual(current.status, 'failed')
                self.assertFalse(snapshots[0].exists())
                return
            if scenario == 'late':
                self.assertFalse(result.success)
                self.assertEqual(result.status, 'pending_timeout')
            else:
                self.assertTrue(result.success)
                self.assertEqual(result.status, 'accepted')
            if scenario in ('cancel', 'slowcancel'):
                self.assertFalse(call('start', 'valid.mission').success)
                self.assertFalse(call('cancel', execution='wrong-current').success)
                canceled = call('cancel', execution=execution)
                self.assertTrue(canceled.success)
                self.assertIn(canceled.status, ('cancel_requested', 'canceled'))
                if scenario == 'slowcancel':
                    self.assertEqual(canceled.status, 'cancel_requested')
                    self.assertEqual(call('query', execution=execution).status, 'canceling')
                    self.assertEqual(call('start', 'valid.mission').status, 'busy')
            until = time.monotonic() + 5
            while time.monotonic() < until:
                result = call('query', execution=execution)
                if result.status in ('succeeded', 'failed', 'canceled') and not result.execution_pending:
                    break
                rclpy.spin_once(node, timeout_sec=0.02)
            expected = 'succeeded' if scenario == 'success' else 'failed' if scenario == 'fail' else 'canceled'
            self.assertEqual(result.status, expected)
            self.assertTrue(snapshots)
            self.assertFalse(snapshots[0].exists())  # Only delete after real terminal.
            if scenario == 'late':
                self.assertEqual(events, ['canceled'])
            if scenario == 'success':
                for i in range(257):
                    (root / f'not-a-mission-{i}.txt').touch()
                limited = call('list')
                self.assertFalse(limited.success)
                self.assertIn('256 directory entries', limited.message)
        except Exception:
            log.seek(0)
            print(log.read())
            raise
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            log.close()
            node.destroy_service(owner)
            if backend:
                backend.destroy()
            if backend_executor:
                backend_executor.shutdown(timeout_sec=5)
                backend_thread.join(timeout=5)
                backend_node.destroy_node()
            node.destroy_node()
            rclpy.shutdown()
            directory.cleanup()

    def test_success(self):
        self.run_scenario('success')

    def test_failure(self):
        self.run_scenario('fail')

    def test_rejection(self):
        self.run_scenario('reject')

    def test_cancel_is_owned(self):
        self.run_scenario('cancel')

    def test_late_admission_is_retained_and_canceled(self):
        self.run_scenario('late')

    def test_cancel_ack_does_not_release_ownership(self):
        self.run_scenario('slowcancel')

    def test_unavailable(self):
        self.run_scenario('unavailable')

    def test_public_terminal_does_not_delete_snapshot_or_release_catalog_slot(self):
        self.run_scenario('managed_drain')

    def test_late_cancel_rejection_cannot_overwrite_real_result_during_drain(self):
        self.run_scenario('late_cancel_reject')


if __name__ == '__main__':
    unittest.main()
