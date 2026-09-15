#!/usr/bin/env python3
"""P0 FlightController contract test with a deterministic mocked vehicle/bridge."""

import math
import sys
import threading
import time

import rclpy
from action_msgs.msg import GoalStatus
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from easyfly_msgs.action import FollowTrajectory, GoToWaypoint, Land, Takeoff
from easyfly_msgs.msg import UAVCommand, UAVState
from easyfly_msgs.srv import ArmMotors, SetFlightMode
from quadrotor_msgs.msg import PositionCommand


def wait_future(future, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not future.done() and time.monotonic() < deadline:
        time.sleep(0.01)
    return future.result() if future.done() else None


class MockVehicle(Node):
    def __init__(self):
        super().__init__("p0_mock_vehicle")
        self.lock = threading.Lock()
        self.state = UAVState()
        self.state.header.frame_id = "odom"
        self.state.connected = True
        self.state.pose_valid = True
        self.state.velocity_valid = True
        self.state.attitude_valid = True
        self.state.battery_valid = True
        self.state.gps_valid = True
        self.state.battery_remaining = 0.8
        self.state.flight_mode = 2
        self.state.flight_mode_name = "POSCTL"
        self.freeze_plant = False
        self.commands = []
        self.pub_state = self.create_publisher(UAVState, "/uav_state", 10)
        self.pub_traj = self.create_publisher(PositionCommand, "/position_cmd", 10)
        self.create_subscription(UAVCommand, "/uav_command", self.on_command, 10)
        self.create_service(ArmMotors, "/arm_motors", self.on_arm)
        self.create_service(SetFlightMode, "/set_flight_mode", self.on_mode)
        self.create_timer(0.02, self.publish_state)
        self.takeoff = ActionClient(self, Takeoff, "/takeoff")
        self.land = ActionClient(self, Land, "/land")
        self.waypoint = ActionClient(self, GoToWaypoint, "/goto_waypoint")
        self.follow = ActionClient(self, FollowTrajectory, "/follow_trajectory")

    def publish_state(self):
        with self.lock:
            self.state.header.stamp = self.get_clock().now().to_msg()
            self.pub_state.publish(self.state)

    def on_command(self, msg):
        with self.lock:
            self.commands.append(msg)
            self.commands = self.commands[-200:]
            if (self.state.armed and self.state.flight_mode == 3 and
                    not self.freeze_plant and msg.control_mode in
                    (UAVCommand.POSITION, UAVCommand.TRAJECTORY)):
                self.state.position_x = msg.position_x
                self.state.position_y = msg.position_y
                self.state.position_z = msg.position_z
                self.state.yaw = msg.yaw

    def on_arm(self, request, response):
        with self.lock:
            self.state.armed = request.arm
        response.success = True
        response.message = "mock"
        return response

    def on_mode(self, request, response):
        names = {3: "OFFBOARD", 6: "AUTO.RTL", 7: "AUTO.LAND"}
        with self.lock:
            self.state.flight_mode = request.flight_mode
            self.state.flight_mode_name = names.get(request.flight_mode, "MOCK")
        response.success = True
        response.message = "mock"
        return response

    def snapshot(self):
        with self.lock:
            return (self.state.position_x, self.state.position_y,
                    self.state.position_z, self.state.armed,
                    self.state.flight_mode)

    def latest_command(self):
        with self.lock:
            return self.commands[-1] if self.commands else None

    def publish_position_command(self, frame="odom", trajectory_id=1,
                                 position_x_delta=2.0, stamp=None):
        x, y, z, _, _ = self.snapshot()
        msg = PositionCommand()
        msg.header.stamp = stamp if stamp is not None else self.get_clock().now().to_msg()
        msg.header.frame_id = frame
        msg.trajectory_flag = PositionCommand.TRAJECTORY_STATUS_READY
        msg.trajectory_id = trajectory_id
        msg.position.x = x + position_x_delta
        msg.position.y = y
        msg.position.z = z
        msg.yaw = 0.0
        self.pub_traj.publish(msg)


def send_goal(client, goal, timeout=10.0):
    response = wait_future(client.send_goal_async(goal), timeout)
    return response if response is not None and response.accepted else None


def result(goal_handle, timeout=10.0):
    response = wait_future(goal_handle.get_result_async(), timeout)
    return (None, None) if response is None else (response.status, response.result)


def check(name, condition):
    print("[%s] %s" % ("PASS" if condition else "FAIL", name), flush=True)
    return bool(condition)


def main():
    rclpy.init()
    node = MockVehicle()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()
    checks = []
    try:
        checks.append(check("action servers ready", all(client.wait_for_server(10.0) for client in
                            (node.takeoff, node.land, node.waypoint, node.follow))))
        time.sleep(0.3)

        takeoff = Takeoff.Goal()
        takeoff.target_altitude = 1.5
        takeoff.climb_speed = 1.0
        gh = send_goal(node.takeoff, takeoff)
        status, _ = result(gh, 15.0) if gh else (None, None)
        checks.append(check("takeoff transaction succeeds", status == GoalStatus.STATUS_SUCCEEDED))

        # The controller reports takeoff success once the vehicle is inside the
        # acceptance band, then changes its hold setpoint to the exact target.
        # Give the mocked plant one control tick to consume that final hold
        # command before using the state as the trajectory pre-hold reference.
        time.sleep(0.2)

        bad = GoToWaypoint.Goal()
        bad.target_x = math.nan
        bad.target_y = 0.0
        bad.target_z = 1.5
        bad.target_yaw = 0.0
        bad.max_speed = 1.0
        bad.acceptance_radius = 0.5
        checks.append(check("non-finite goal rejected", send_goal(node.waypoint, bad, 3.0) is None))

        x, y, z, _, _ = node.snapshot()
        follow = FollowTrajectory.Goal()
        follow.target_x, follow.target_y, follow.target_z = x + 10.0, y, z
        follow.acceptance_radius = 0.5
        follow.timeout = 30.0

        # A fresh old-ID stream may still be present when a new goal is
        # accepted.  It must remain a hover hold until the planner publishes a
        # strictly newer trajectory ID.
        old_id = 100
        for _ in range(10):
            node.publish_position_command(trajectory_id=old_id)
            time.sleep(0.02)
        time.sleep(0.1)
        gh = send_goal(node.follow, follow)
        old_goal_result = gh.get_result_async() if gh is not None else None
        for _ in range(80):
            node.publish_position_command(trajectory_id=old_id)
            time.sleep(0.005)
        time.sleep(0.2)
        hold = node.latest_command()
        checks.append(check("old trajectory ID cannot activate new goal",
                            gh is not None and hold is not None and
                            old_goal_result is not None and not old_goal_result.done() and
                            hold.control_mode == UAVCommand.POSITION and
                            abs(hold.position_z - z) < 0.2))

        node.publish_position_command(frame="map", trajectory_id=old_id + 1)
        time.sleep(0.2)
        checks.append(check("wrong trajectory frame rejected",
                            node.latest_command().control_mode == UAVCommand.POSITION))

        wait_future(gh.cancel_goal_async())
        status, _ = result(gh)
        checks.append(check("trajectory wait cancel is CANCELED",
                            status == GoalStatus.STATUS_CANCELED))

        node.freeze_plant = True
        pre_goal_stamp = node.get_clock().now().to_msg()
        time.sleep(0.1)
        gh = send_goal(node.follow, follow)
        # 高频发送一个时间戳早于本次 goal 的 N+1，覆盖 response/accepted
        # 窗口；被 time 检查拒绝后，同 ID 的新鲜帧仍必须能够启动。
        for _ in range(80):
            node.publish_position_command(
                trajectory_id=old_id + 1, stamp=pre_goal_stamp)
            time.sleep(0.005)
        time.sleep(0.2)
        checks.append(check("old-time N+1 stays in trajectory wait",
                            node.latest_command().control_mode == UAVCommand.POSITION))

        node.publish_position_command(trajectory_id=old_id + 1)
        time.sleep(0.2)
        checks.append(check("new trajectory ID activates trajectory",
                            node.latest_command().control_mode == UAVCommand.TRAJECTORY))
        checks.append(check("valid trajectory reaches TRAJECTORY encoder",
                            node.latest_command().control_mode == UAVCommand.TRAJECTORY))

        active_before_rollback = node.latest_command()
        node.publish_position_command(
            trajectory_id=old_id, position_x_delta=-7.0)
        time.sleep(0.2)
        active_after_rollback = node.latest_command()
        checks.append(check("active trajectory rejects rollback ID",
                            active_before_rollback is not None and
                            active_after_rollback is not None and
                            active_after_rollback.control_mode == UAVCommand.TRAJECTORY and
                            abs(active_after_rollback.position_x -
                                active_before_rollback.position_x) < 0.2))

        end_stream = time.monotonic() + 0.8
        while time.monotonic() < end_stream:
            node.publish_position_command(trajectory_id=old_id + 1)
            time.sleep(0.02)
        status, res = result(gh, 3.0)
        checks.append(check("trajectory stream loss aborts explicitly",
                            status == GoalStatus.STATUS_ABORTED and
                            res is not None and res.message == "stream_lost"))

        wp1 = GoToWaypoint.Goal()
        wp1.target_x, wp1.target_y, wp1.target_z = x + 10.0, y, z
        wp1.target_yaw, wp1.max_speed, wp1.acceptance_radius = 0.0, 1.0, 0.5
        wp2 = GoToWaypoint.Goal()
        wp2.target_x, wp2.target_y, wp2.target_z = x - 10.0, y, z
        wp2.target_yaw, wp2.max_speed, wp2.acceptance_radius = 0.0, 1.0, 0.5
        f1 = node.waypoint.send_goal_async(wp1)
        f2 = node.waypoint.send_goal_async(wp2)
        g1, g2 = wait_future(f1), wait_future(f2)
        accepted = [g for g in (g1, g2) if g is not None and g.accepted]
        checks.append(check("concurrent goals reserve one slot", len(accepted) == 1))
        if accepted:
            wait_future(accepted[0].cancel_goal_async())
            status, _ = result(accepted[0])
            checks.append(check("waypoint cancel is CANCELED",
                                status == GoalStatus.STATUS_CANCELED))

        land = Land.Goal()
        land.landing_speed = 0.0
        gh = send_goal(node.land, land)
        time.sleep(0.3)
        wait_future(gh.cancel_goal_async(), 10.0)
        status, _ = result(gh, 10.0)
        _, _, _, armed, mode = node.snapshot()
        checks.append(check("land cancel confirms OFFBOARD before CANCELED",
                            status == GoalStatus.STATUS_CANCELED and armed and mode == 3))
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
