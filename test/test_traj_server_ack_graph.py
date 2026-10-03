"""Opt-in ROS graph test for the dedicated traj_server ACK contract.

The ordinary contract suite stays ROS-free.  Run this test after sourcing the
build-v2/install-v2 overlay with ``E4_RUN_ROS_GRAPH=1``.  It starts the real
installed traj_server, sends one valid and one rejected B-spline, and checks
that only the accepted candidate produces TrajectoryAck.  fake/multi-publisher
source rejection is covered by the production callback's GID/graph gate and
the companion EmergencyRecoveryGate GTest; this harness deliberately does not
replace that deterministic unit test with an unsafe fake ACK.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("E4_RUN_ROS_GRAPH") != "1",
    reason="opt-in: starts a real traj_server/DDS graph; use E4_RUN_ROS_GRAPH=1",
)

if os.environ.get("E4_RUN_ROS_GRAPH") == "1":
    import rclpy
    from geometry_msgs.msg import Point
    from rclpy.duration import Duration
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
    from traj_utils.msg import Bspline, TrajectoryAck


def _spin_until(node, predicate, timeout_s=5.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.05)
        if predicate():
            return True
    return False


def _message(*, traj_id, order=3, start_time=None):
    msg = Bspline()
    msg.drone_id = 0
    msg.order = order
    msg.traj_id = traj_id
    msg.start_time = start_time
    msg.knots = [0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0]
    msg.pos_pts = [
        Point(x=0.0, y=0.0, z=1.0),
        Point(x=0.3, y=0.0, z=1.0),
        Point(x=0.6, y=0.0, z=1.0),
        Point(x=0.9, y=0.0, z=1.0),
    ]
    msg.yaw_pts = []
    msg.yaw_dt = 0.0
    return msg


def test_real_traj_server_ack_graph_accepts_only_valid_candidate():
    assert shutil.which("ros2"), "source ROS 2 and install-v2 before this opt-in test"

    rclpy.init()
    node = rclpy.create_node(f"e4_ack_graph_probe_{os.getpid()}")
    suffix = str(os.getpid())
    bspline_topic = f"/e4_ack_graph_{suffix}/planning/bspline"
    ack_topic = f"/e4_ack_graph_{suffix}/trajectory_ack"
    cmd_topic = f"/e4_ack_graph_{suffix}/position_cmd"
    process = None
    received = []
    try:
        qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        node.create_subscription(
            TrajectoryAck, ack_topic, lambda msg: received.append(msg), qos)
        publisher = node.create_publisher(Bspline, bspline_topic, 10)
        process = subprocess.Popen(
            [
                "ros2", "run", "ego_planner", "traj_server", "--ros-args",
                "-r", f"planning/bspline:={bspline_topic}",
                "-r", f"trajectory_ack:={ack_topic}",
                "-r", f"position_cmd:={cmd_topic}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        assert _spin_until(
            node, lambda: process.poll() is None and node.count_subscribers(bspline_topic) > 0,
            timeout_s=8.0), "traj_server did not expose the Bspline subscription"

        start = node.get_clock().now() + Duration(seconds=0.2)
        valid = _message(traj_id=101, start_time=start.to_msg())
        publisher.publish(valid)
        assert _spin_until(node, lambda: any(a.trajectory_id == 101 for a in received)), \
            "valid B-spline did not produce a dedicated ACK"
        accepted_count = len(received)

        rejected = _message(traj_id=102, order=1, start_time=start.to_msg())
        publisher.publish(rejected)
        time.sleep(0.2)
        _spin_until(node, lambda: False, timeout_s=0.5)
        assert len(received) == accepted_count, "rejected B-spline emitted an ACK"
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=3.0)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    pass
