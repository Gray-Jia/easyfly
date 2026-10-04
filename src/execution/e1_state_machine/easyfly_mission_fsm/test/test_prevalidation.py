"""Real executor rejects an invalid later step before sending any flight goal."""
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest

import rclpy
from rclpy.action import ActionClient, ActionServer
from easyfly_msgs.action import ExecuteMission, Takeoff
from easyfly_msgs.msg import UAVState


class PrevalidationTest(unittest.TestCase):
    def test_shared_validation_is_used_by_actual_executor(self):
        rclpy.init()
        node = rclpy.create_node('mission_prevalidation_test')
        calls = []
        def unexpected_takeoff(handle):
            calls.append(handle.request)
            handle.abort()
            return Takeoff.Result(success=False)
        mock = ActionServer(node, Takeoff, '/takeoff', unexpected_takeoff)
        pub = node.create_publisher(UAVState, '/uav_state', 10)
        def telemetry():
            message = UAVState(connected=True, pose_valid=True, battery_valid=True, battery_remaining=1.0)
            message.header.frame_id = 'odom'
            message.header.stamp = node.get_clock().now().to_msg()
            pub.publish(message)
        timer = node.create_timer(0.02, telemetry)
        client = ActionClient(node, ExecuteMission, '/execute_mission')
        log = tempfile.TemporaryFile(mode='w+')
        process = subprocess.Popen(['ros2', 'run', 'easyfly_mission_fsm', 'mission_fsm_node'],
                                   stdout=log, stderr=log, start_new_session=True)
        temporary = tempfile.TemporaryDirectory(prefix='easyfly-d2-prevalidation-')
        def wait(future):
            until = time.monotonic() + 5
            while not future.done() and time.monotonic() < until:
                rclpy.spin_once(node, timeout_sec=0.01)
            self.assertTrue(future.done())
            return future.result()
        try:
            self.assertTrue(client.wait_for_server(timeout_sec=5))
            until = time.monotonic() + 0.3
            while time.monotonic() < until:
                rclpy.spin_once(node, timeout_sec=0.01)
            bad = Path(temporary.name) / 'bad.mission'
            bad.write_text('type=takeoff\naltitude=2\n---\ntype=hover\nwait=not-a-number\n')
            handle = wait(client.send_goal_async(ExecuteMission.Goal(mission_file=str(bad))))
            if handle.accepted:
                result = wait(handle.get_result_async())
                self.assertEqual(result.status, 6)
            self.assertFalse(calls)
            good = Path(temporary.name) / 'good.mission'
            good.write_text('type=hover\nwait=0.1\n')
            handle = wait(client.send_goal_async(ExecuteMission.Goal(mission_file=str(good))))
            self.assertTrue(handle.accepted)
            result = wait(handle.get_result_async())
            self.assertEqual(result.status, 4)
            self.assertTrue(result.result.success)
            self.assertFalse(calls)
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
            mock.destroy()
            client.destroy()
            node.destroy_node()
            rclpy.shutdown()
            temporary.cleanup()


if __name__ == '__main__':
    unittest.main()
