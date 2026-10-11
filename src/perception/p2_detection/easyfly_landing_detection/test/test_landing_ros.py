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

import csv
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest
import rclpy
from easyfly_msgs.msg import TagObservationArray, TagObservation, LandingTarget


class LandingRos(unittest.TestCase):
    def test_explicit_selection_loss_bad_pose_and_expiration(self):
        rclpy.init()
        node = rclpy.create_node('landing_test')
        outputs = []
        self.addCleanup(rclpy.shutdown)
        self.addCleanup(node.destroy_node)
        pub = node.create_publisher(
            TagObservationArray, '/tag_observations', 10
        )
        node.create_subscription(
            LandingTarget, '/landing_target', outputs.append, 10
        )
        log = tempfile.TemporaryFile(mode='w+')
        self.addCleanup(log.close)
        evidence = tempfile.TemporaryDirectory(prefix='easyfly-landing-ingress-')
        self.addCleanup(evidence.cleanup)
        trace = Path(evidence.name) / 'ingress.tsv'
        process = subprocess.Popen(
            [
                'ros2',
                'run',
                'easyfly_landing_detection',
                'landing_detection_node',
                '--ros-args',
                '-p',
                'selected_tag_id:=7',
                '-p',
                f'timing_trace_path:={trace}',
            ],
            stdout=log,
            stderr=log,
            start_new_session=True,
        )

        def stop():
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)

        self.addCleanup(stop)

        def spin(seconds):
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                rclpy.spin_once(node, timeout_sec=0.01)

        def send(kind):
            outputs.clear()
            m = TagObservationArray(valid=True)
            m.header.frame_id = 'camera_color_optical_frame'
            m.header.stamp = node.get_clock().now().to_msg()
            o = TagObservation(tag_id=7, tag_size_m=0.2, valid=True)
            o.header = m.header
            o.pose.position.z = 2.0
            o.pose.orientation.w = 1.0
            m.observations = [o]
            if kind == 'empty':
                m.observations = []
            elif kind == 'other':
                o.tag_id = 8
            elif kind == 'duplicate':
                m.observations = [o, o]
            elif kind == 'quat':
                o.pose.orientation.w = 2.0
            elif kind == 'depth':
                o.pose.position.z = -1.0
            elif kind == 'invalid':
                m.valid = False
            elif kind == 'frame':
                m.header.frame_id = 'map'
            pub.publish(m)
            spin(0.12)
            self.assertTrue(outputs)
            return outputs[-1]

        try:
            spin(0.4)
            good = send('good')
            self.assertTrue(good.valid)
            self.assertEqual(good.optical_depth_m, 2.0)
            self.assertEqual(good.yaw_rad, 0.0)
            for kind in (
                'empty',
                'other',
                'duplicate',
                'quat',
                'depth',
                'invalid',
                'frame',
            ):
                self.assertFalse(send(kind).valid, kind)
            self.assertTrue(send('good').valid)
            spin(0.65)
            self.assertFalse(outputs[-1].valid)
            self.assertEqual(trace.stat().st_size, 0, 'no callback-time trace I/O')
        finally:
            stop()
            log.close()
        with trace.open() as stream:
            metadata = stream.readline()
            self.assertIn('dropped=0', metadata)
            events = list(csv.DictReader(stream, delimiter='\t'))
        self.assertTrue(events)
        self.assertTrue(any(e['input'] == '0' for e in events))
        good = [e for e in events if e['valid'] == '1']
        self.assertTrue(good)
        for event in good:
            self.assertEqual(event['input'], '1')
            self.assertGreater(int(event['writer_wall_ns']), 0)
            self.assertGreater(int(event['receive_wall_ns']), 0)
            self.assertGreaterEqual(int(event['publish_end_wall_ns']),
                                    int(event['publish_begin_wall_ns']))
            self.assertGreaterEqual(int(event['publish_begin_wall_ns']),
                                    int(event['entry_wall_ns']))


if __name__ == '__main__':
    unittest.main()
