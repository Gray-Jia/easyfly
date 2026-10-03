#!/usr/bin/env python3
"""
ego_acceptance.py — M4.3 EGO-Planner 集成验收 (轻链: perception_demo.world)

用例:
  E1  静态绕障   立柱 (perception_demo.world pillar, 3m): hover → 自锚定立柱 →
                 从新鲜成对障碍证据选取对侧安全终点、保持 hover 高度 →
                 FollowTrajectory(目标=立柱对侧) + EGO goal: SUCCEEDED、
                 全程与立柱中心 min > 0.8m、落点误差 < 1.0m
  E2  动态重规划 patrol 行人横穿航线: EGO 在线重规划、与障碍中心 min > 0.8m、仍到达
  E4  接管让位   基于同步 /obstacles+/occupancy_grid 选局部安全目标并确认新轨迹流后切 RTL
                 → FollowTrajectory abort (takeover)
  E3  流中断安全 基于同步 /obstacles+/occupancy_grid 选局部安全目标并确认新轨迹流后杀 traj_server
                 → 0.5s 内回悬停 (z 保持, abort stream_lost)
  (E5 = run_control_regression.sh 全绿, 由编排器外部执行)

前置: run_ego_acceptance.sh 已启动 test/ego_acceptance.launch.py
退出码: 0=全部硬断言通过

自锚定约定 (与 M4.0/M4.2 一致): 禁止锚定 gazebo 世界坐标 (odom↔world 每会话随机偏移),
障碍位置一律从 /obstacles 票选得到。

注意: FollowTrajectory 进入条件为 HOVER; 且 EGO traj_server 在收到首条 bspline 前不发布
      /position_cmd, 故顺序必须是 "先发 follow goal (等首帧宽限) → 再发 EGO goal", 避免
      转发到上一条残留轨迹造成 setpoint 跳变。
"""

import math
import subprocess
import sys
import threading
import time
from collections import Counter

try:
    from ego_e2_admission import (
        E2_FUTURE_TOLERANCE_S,
        E2_MAX_ARRIVAL_AGE_S,
        E2_MAX_MESSAGE_AGE_S,
        admit_e2_pair,
    )
    from trajectory_admission import goal_is_active, is_new_goal_trajectory
    from ego_e1_admission import (
        E1_MAX_POSE_ALTITUDE_TOLERANCE_M,
        E1_MAX_PLANNER_ALTITUDE_M,
        E1_REQUIRED_CLEARANCE_M,
        admitted_hover_altitude,
        e1_pose_height_within_policy,
        select_e1_opposite_goal,
    )
    from ego_local_goal_admission import (
        LOCAL_GOAL_MAX_GRID_CELLS,
        LOCAL_GOAL_MAX_GRID_DIMENSION,
        admit_occupancy_grid_evidence,
        select_local_safe_goal,
    )
except ModuleNotFoundError:
    # This form is useful when the script is imported from the workspace root
    # by pytest rather than executed as ``python test/ego_acceptance.py``.
    from test.ego_e2_admission import (
        E2_FUTURE_TOLERANCE_S,
        E2_MAX_ARRIVAL_AGE_S,
        E2_MAX_MESSAGE_AGE_S,
        admit_e2_pair,
    )
    from test.trajectory_admission import goal_is_active, is_new_goal_trajectory
    from test.ego_e1_admission import (
        E1_MAX_POSE_ALTITUDE_TOLERANCE_M,
        E1_MAX_PLANNER_ALTITUDE_M,
        E1_REQUIRED_CLEARANCE_M,
        admitted_hover_altitude,
        e1_pose_height_within_policy,
        select_e1_opposite_goal,
    )
    from test.ego_local_goal_admission import (
        LOCAL_GOAL_MAX_GRID_CELLS,
        LOCAL_GOAL_MAX_GRID_DIMENSION,
        admit_occupancy_grid_evidence,
        select_local_safe_goal,
    )

import rclpy
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import QoSProfile

from action_msgs.msg import GoalStatus
from easyfly_msgs.action import FollowTrajectory, Takeoff
from easyfly_msgs.msg import ObstacleInfoArray, UAVState
from easyfly_msgs.srv import SetFlightMode
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import OccupancyGrid
from quadrotor_msgs.msg import PositionCommand

GSTATUS = {
    GoalStatus.STATUS_SUCCEEDED: "SUCCEEDED",
    GoalStatus.STATUS_CANCELED: "CANCELED",
    GoalStatus.STATUS_ABORTED: "ABORTED",
    GoalStatus.STATUS_ACCEPTED: "ACCEPTED",
    GoalStatus.STATUS_EXECUTING: "EXECUTING",
}

# 立柱真值 (perception_demo.world): 供日志参考, 判定一律用自锚定值
PILLAR_GAZEBO = (5.0, -2.0)
# perception_demo.world patrol person moves on x=14..22 at y=-2.  Keep the
# E2 goal three metres beyond that endpoint: the route still crosses the full
# patrol work area, while the terminal point is not itself an occupied moving
# target.  This is a scenario-geometry contract, not a relaxed clearance gate.
E2_PATROL_END_OFFSET_M = 17.0
E2_GOAL_CLEARANCE_BEYOND_PATROL_M = 3.0


class EgoAcceptance(Node):

    def __init__(self):
        super().__init__(
            "ego_acceptance",
            parameter_overrides=[Parameter("use_sim_time", value=True)],
        )
        self._lock = threading.Lock()
        self.obs = None
        self.state = None
        self.grid = None
        self.fb = None
        self.pillar = None    # E1 锚定的立柱 (供 E2 相对定位巡逻段)
        self.pos_samples = []   # (t, x, y, z)
        self.last_state_diag = None
        self.last_obs_diag = None
        self.last_grid_diag = None
        self.position_cmd_count = 0
        self.position_cmd_id = None
        self.position_cmd_last_time = 0.0
        # (arrival_mono, count, trajectory_id, position_xyz, velocity_xyz)
        self.position_cmd_history = []
        self.create_subscription(ObstacleInfoArray, "/obstacles",
                                 self._on_obs, QoSProfile(depth=5))
        self.create_subscription(UAVState, "/uav_state",
                                 self._on_state, QoSProfile(depth=10))
        # The semantic-map publisher emits a real OccupancyGrid in odom.  Keep
        # a copied, ROS-free record so goal admission can validate metadata and
        # query cells without reading a mutable message from another callback.
        self.create_subscription(OccupancyGrid, "/occupancy_grid",
                                 self._on_grid, QoSProfile(depth=5))
        self.create_subscription(FollowTrajectory.Impl.FeedbackMessage,
                                 "/follow_trajectory/_action/feedback",
                                 self._on_fb, QoSProfile(depth=50))
        # E4/E3 must distinguish a newly generated EGO trajectory from an
        # old traj_server stream before they exercise takeover or stream-loss.
        self.create_subscription(PositionCommand, "/position_cmd",
                                 self._on_position_cmd, QoSProfile(depth=50))
        self.ac_takeoff = ActionClient(self, Takeoff, "/takeoff")
        self.ac_follow = ActionClient(self, FollowTrajectory, "/follow_trajectory")
        self.cli_mode = self.create_client(SetFlightMode, "/set_flight_mode")
        self.pub_goal = self.create_publisher(PoseStamped, "/move_base_simple/goal", 10)
        self._result_futures = {}

    # ------------------------------------------------ 订阅

    @staticmethod
    def _stamp_parts(stamp):
        try:
            sec = int(stamp.sec)
            nanosec = int(stamp.nanosec)
        except (AttributeError, TypeError, ValueError, OverflowError):
            return None
        if sec < 0 or nanosec < 0 or nanosec >= 1000000000:
            return None
        return sec, nanosec

    def _node_ros_snapshot(self):
        """Read the node clock without allowing clock/type errors to escape.

        The diagnostic path must never crash the acceptance executor.  The
        clock type is retained so a wall-clock/sim-clock mix-up is visible in
        the failure record instead of being silently converted to a number.
        """
        try:
            clock = self.get_clock()
            now = clock.now()
            now_ns = int(now.nanoseconds)
            return {
                "node_ros_ns": now_ns,
                "node_ros": now_ns / 1.0e9,
                "clock_type": str(clock.clock_type),
                "clock_error": None,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "node_ros_ns": None,
                "node_ros": float("nan"),
                "clock_type": "unknown",
                "clock_error": "%s: %s" % (type(exc).__name__, exc),
            }

    def _message_diag(self, stamp, frame_id, arrival_mono, arrival_wall):
        diag = {
            "arrival_mono": float(arrival_mono),
            "arrival_wall": float(arrival_wall),
            "frame_id": str(frame_id or ""),
            "stamp_valid": False,
            "stamp_sec": None,
            "stamp_nanosec": None,
            "age": float("nan"),
            "clock_mismatch": False,
            "error": None,
        }
        parts = self._stamp_parts(stamp)
        clock = self._node_ros_snapshot()
        diag.update(clock)
        if parts is None:
            diag["error"] = "invalid timestamp fields"
            return diag
        sec, nanosec = parts
        diag["stamp_sec"] = sec
        diag["stamp_nanosec"] = nanosec
        if sec == 0 and nanosec == 0:
            diag["error"] = "zero timestamp"
            return diag
        if clock["node_ros_ns"] is None:
            diag["error"] = clock["clock_error"] or "node clock unavailable"
            return diag
        try:
            stamp_ns = sec * 1000000000 + nanosec
            age = (clock["node_ros_ns"] - stamp_ns) / 1.0e9
        except (OverflowError, TypeError, ValueError):
            diag["error"] = "timestamp cannot be converted"
            return diag
        if not math.isfinite(age):
            diag["error"] = "non-finite message age"
            return diag
        diag["stamp_valid"] = True
        diag["age"] = age
        # A ROS header has no clock-domain tag.  A very large age is the
        # actionable evidence of a wall/sim clock mix-up; retain the raw age
        # and mark it rather than letting it affect the 0.8m verdict.
        diag["clock_mismatch"] = abs(age) > 300.0
        if diag["clock_mismatch"]:
            diag["error"] = "message age suggests clock-domain mismatch"
        return diag

    @staticmethod
    def _format_message_diag(diag):
        if not diag:
            return "unavailable"
        sec = diag.get("stamp_sec")
        nsec = diag.get("stamp_nanosec")
        stamp = ("%d.%09d" % (sec, nsec)
                 if isinstance(sec, int) and isinstance(nsec, int)
                 else "invalid")
        age = diag.get("age", float("nan"))
        age_text = "%.3fs" % age if math.isfinite(float(age)) else "nan"
        node_ros = diag.get("node_ros", float("nan"))
        node_text = ("%.9f" % node_ros if math.isfinite(float(node_ros))
                     else "nan")
        suffix = " error=%s" % diag["error"] if diag.get("error") else ""
        return (
            "frame=%s stamp=%s arrival_mono=%.6f arrival_wall=%.3f "
            "node_ros=%s age=%s clock=%s mismatch=%s%s" %
            (diag.get("frame_id", ""), stamp,
             float(diag.get("arrival_mono", float("nan"))),
             float(diag.get("arrival_wall", float("nan"))), node_text,
             age_text, diag.get("clock_type", "unknown"),
             bool(diag.get("clock_mismatch", False)), suffix))

    def _on_obs(self, msg):
        arrival_mono = time.monotonic()
        arrival_wall = time.time()
        diag = self._message_diag(msg.header.stamp, msg.header.frame_id,
                                  arrival_mono, arrival_wall)
        with self._lock:
            self.obs = msg
            self.last_obs_diag = diag

    def _on_state(self, msg):
        arrival_mono = time.monotonic()
        arrival_wall = time.time()
        diag = self._message_diag(msg.header.stamp, msg.header.frame_id,
                                  arrival_mono, arrival_wall)
        with self._lock:
            self.state = msg
            self.last_state_diag = diag
            self.pos_samples.append((time.monotonic(), msg.position_x,
                                     msg.position_y, msg.position_z))
            if len(self.pos_samples) > 8000:
                self.pos_samples = self.pos_samples[-4000:]

    def _on_grid(self, msg):
        arrival_mono = time.monotonic()
        arrival_wall = time.time()
        diag = self._message_diag(msg.header.stamp, msg.header.frame_id,
                                  arrival_mono, arrival_wall)
        try:
            info_msg = msg.info
            resolution = float(info_msg.resolution)
            width = int(info_msg.width)
            height = int(info_msg.height)
            raw_data = msg.data
            cell_count = width * height
            # Do all coarse dimension/length checks before copying the ROS
            # sequence.  A malformed publisher must not make the acceptance
            # node allocate an unbounded tuple merely to reject it later.
            if (not math.isfinite(resolution) or resolution <= 0.0 or
                    width <= 0 or height <= 0 or
                    width > LOCAL_GOAL_MAX_GRID_DIMENSION or
                    height > LOCAL_GOAL_MAX_GRID_DIMENSION or
                    cell_count > LOCAL_GOAL_MAX_GRID_CELLS or
                    len(raw_data) != cell_count):
                raise ValueError("occupancy grid dimensions/data length invalid")
            origin = info_msg.origin
            origin_values = (
                float(origin.position.x), float(origin.position.y),
                float(origin.position.z), float(origin.orientation.x),
                float(origin.orientation.y), float(origin.orientation.z),
                float(origin.orientation.w))
            if not all(math.isfinite(value) for value in origin_values):
                raise ValueError("occupancy grid origin is non-finite")
            qx, qy, qz, qw = origin_values[3:]
            qnorm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
            if (not math.isfinite(qnorm) or abs(qnorm - 1.0) > 1.0e-3 or
                    abs(qx) > 1.0e-3 or abs(qy) > 1.0e-3 or
                    abs(qz) > 1.0e-3 or abs(abs(qw) - 1.0) > 1.0e-3):
                raise ValueError("occupancy grid origin quaternion invalid")
            # The size has already been bounded above; this is now a bounded
            # copy and conversion.  Metadata/data value normalization remains
            # in the ROS-free helper so tests and runtime share one contract.
            data = tuple(int(value) for value in raw_data)
            grid = {
                "frame_id": str(msg.header.frame_id or ""),
                "diag": diag,
                "resolution": resolution,
                "width": width,
                "height": height,
                "origin_x": origin_values[0],
                "origin_y": origin_values[1],
                "origin_z": origin_values[2],
                "origin_qx": origin_values[3],
                "origin_qy": origin_values[4],
                "origin_qz": origin_values[5],
                "origin_qw": origin_values[6],
                # Copy the bounded sequence: a callback may receive the next
                # ROS message while a goal candidate is being checked.
                "data": data,
            }
        except (AttributeError, TypeError, ValueError, OverflowError):
            # Preserve the diagnostic so a malformed message is reported as a
            # deterministic evidence rejection rather than an executor error.
            grid = {"frame_id": str(getattr(msg.header, "frame_id", "") or ""),
                    "diag": diag, "data": ()}
        with self._lock:
            self.grid = grid
            self.last_grid_diag = diag

    def _on_fb(self, msg):
        with self._lock:
            self.fb = msg.feedback

    def _on_position_cmd(self, msg):
        if msg.trajectory_flag != PositionCommand.TRAJECTORY_STATUS_READY:
            return
        arrival_mono = time.monotonic()
        with self._lock:
            self.position_cmd_count += 1
            self.position_cmd_id = int(msg.trajectory_id)
            self.position_cmd_last_time = arrival_mono
            position = (float(msg.position.x), float(msg.position.y),
                        float(msg.position.z))
            velocity = (float(msg.velocity.x), float(msg.velocity.y),
                        float(msg.velocity.z))
            self.position_cmd_history.append(
                (arrival_mono, self.position_cmd_count, self.position_cmd_id,
                 position, velocity))
            if len(self.position_cmd_history) > 2000:
                self.position_cmd_history = self.position_cmd_history[-1000:]

    def snap(self):
        with self._lock:
            return self.state

    def last_pos(self):
        with self._lock:
            if not self.pos_samples:
                return None
            t, x, y, z = self.pos_samples[-1]
            return (x, y, z)

    def min_dist_to_point(self, t_start, px, py):
        sample = self.closest_sample_to_point(t_start, px, py)
        return sample[0] if sample is not None else float("nan")

    def closest_sample_to_point(self, t_start, px, py):
        """Return (distance, t, x, y, z) for the closest post-goal sample.

        E1 still evaluates the unchanged center-distance >0.8m contract.  The
        extra pose is diagnostic evidence: it distinguishes a real near-pass
        from a stale/incorrect anchor or a sampler bug without changing the
        verdict or threshold.
        """
        with self._lock:
            samples = [(math.hypot(x - px, y - py), t, x, y, z)
                       for t, x, y, z in self.pos_samples if t >= t_start]
        return min(samples, key=lambda item: item[0]) if samples else None

    def max_sample_z_since(self, t_start):
        """Return the maximum finite post-goal altitude, or NaN if absent."""
        with self._lock:
            heights = [z for t, _, _, z in self.pos_samples
                       if t >= t_start and math.isfinite(float(z))]
        return max(heights) if heights else float("nan")

    def position_cmd_snapshot(self):
        with self._lock:
            return self.position_cmd_count, self.position_cmd_id

    def first_new_trajectory_after(self, after_mono, baseline_count, baseline_id):
        with self._lock:
            for arrival_mono, count, trajectory_id, _, _ in self.position_cmd_history:
                if (arrival_mono >= after_mono and count > baseline_count and
                        trajectory_id is not None and trajectory_id != baseline_id):
                    return arrival_mono, trajectory_id
        return None, None

    def wait_for_new_trajectory(self, baseline_count, baseline_id,
                                timeout_s=8.0, origin=None, target=None):
        """Wait for a READY stream with a new planner trajectory id.

        A message count or changed trajectory_id alone is insufficient because
        an emergency-stop spline may also receive a fresh ID.  For E3/E4 the
        caller supplies the requested goal and the command must also show
        finite, non-trivial progress toward that goal.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            with self._lock:
                history = list(self.position_cmd_history)
            for _, count, trajectory_id, position, velocity in history:
                if count <= baseline_count or trajectory_id is None:
                    continue
                if baseline_id is not None and trajectory_id == baseline_id:
                    continue
                if origin is None or target is None:
                    return trajectory_id
                if is_new_goal_trajectory(
                    baseline_count, baseline_id, count, trajectory_id,
                    origin, target, position, velocity):
                    return trajectory_id
            time.sleep(0.05)
        return None

    def cancel_goal(self, gh):
        """Best-effort cancellation for a goal that never produced a stream."""
        if gh is None:
            return
        try:
            self._wait_future(gh.cancel_goal_async(), 5.0)
            self.wait_result(gh, 5.0)
        except Exception as exc:  # noqa: BLE001
            info("取消未启动的 FollowTrajectory goal: %s" % exc)

    @staticmethod
    def _xy_obstacle_clearance(x, y, obstacle):
        values = (obstacle.center_x, obstacle.center_y,
                  obstacle.size_x, obstacle.size_y)
        if not all(math.isfinite(float(v)) for v in values):
            return float("-inf")
        hx = max(0.15, abs(float(obstacle.size_x)) * 0.5)
        hy = max(0.15, abs(float(obstacle.size_y)) * 0.5)
        dx = max(abs(x - float(obstacle.center_x)) - hx, 0.0)
        dy = max(abs(y - float(obstacle.center_y)) - hy, 0.0)
        return math.hypot(dx, dy)

    def _admitted_obstacle_snapshot(self):
        """Return an obstacle snapshot only with the same evidence gate as E2.

        E3/E4 used to select a goal from whichever latched ``/obstacles``
        message happened to be present.  Requiring the paired fresh UAVState
        and identical odom/clock/timestamp/arrival checks makes a stale or
        cross-frame candidate fail closed before any geometry is considered.
        """
        with self._lock:
            state = self.state
            obs_msg = self.obs
            state_diag = dict(self.last_state_diag or {})
            obs_diag = dict(self.last_obs_diag or {})
        if state is None or obs_msg is None:
            return None, ("state_missing" if state is None else "obstacles_missing",)
        state_fields = {
            "connected": bool(state.connected),
            "pose_valid": bool(state.pose_valid),
            "position_x": state.position_x,
            "position_y": state.position_y,
            "position_z": state.position_z,
        }
        current_ros = self._node_ros_snapshot()
        admitted, reasons = admit_e2_pair(
            state_fields, state_diag, obs_diag, time.monotonic(),
            now_ros_ns=current_ros.get("node_ros_ns"))
        if not admitted:
            return None, reasons
        return list(obs_msg.obstacles), ()

    def _admitted_local_goal_snapshot(self):
        """Return obstacles + occupancy grid from one synchronized snapshot.

        E3/E4 are intentionally stricter than E1/E2's obstacle-only geometry:
        a fresh obstacle box does not prove that the space beyond it was
        observed.  The grid must be fresh in the same odom/clock domain and
        synchronized by both ROS stamp and callback-monotonic arrival.
        """
        with self._lock:
            state = self.state
            obs_msg = self.obs
            grid = dict(self.grid) if isinstance(self.grid, dict) else self.grid
            state_diag = dict(self.last_state_diag or {})
            obs_diag = dict(self.last_obs_diag or {})
        if state is None or obs_msg is None or grid is None:
            missing = []
            if state is None:
                missing.append("state_missing")
            if obs_msg is None:
                missing.append("obstacles_missing")
            if grid is None:
                missing.append("occupancy_grid_missing")
            return None, None, tuple(missing)
        state_fields = {
            "connected": bool(state.connected),
            "pose_valid": bool(state.pose_valid),
            "position_x": state.position_x,
            "position_y": state.position_y,
            "position_z": state.position_z,
        }
        now_mono = time.monotonic()
        current_ros = self._node_ros_snapshot()
        admitted, reasons = admit_e2_pair(
            state_fields, state_diag, obs_diag, now_mono,
            now_ros_ns=current_ros.get("node_ros_ns"))
        grid_admitted, grid_reasons = admit_occupancy_grid_evidence(
            grid, state_diag, obs_diag, now_mono,
            now_ros_ns=current_ros.get("node_ros_ns"))
        all_reasons = list(reasons)
        for reason in grid_reasons:
            if reason not in all_reasons:
                all_reasons.append(reason)
        if not admitted or not grid_admitted:
            return None, None, tuple(all_reasons)
        return list(obs_msg.obstacles), grid, ()

    def pick_local_safe_goal(self, p0, z=None, clearance=0.8):
        """Pick a short goal from synchronized obstacle/grid evidence.

        The helper caps motion well inside the planner's 5.5m local update
        window, then applies an additional obstacle-derived range cap.  AABBs
        are never treated as proof that unobserved free space is safe: every
        sampled segment point must pass the fresh, already-inflated
        occupancy-grid centerline query as well as strict obstacle clearance.
        No synchronized state,
        obstacle, grid, hover altitude or candidate means an explicit failure.
        """
        obstacles, occupancy_grid, reasons = self._admitted_local_goal_snapshot()
        if obstacles is None:
            info("拒绝 E3/E4 局部目标: /uav_state + /obstacles + "
                 "/occupancy_grid 未通过同步准入 (%s)" %
                 ",".join(reasons) if reasons else "unknown")
            return None
        state = self.snap()
        hover_z = admitted_hover_altitude(
            state.position_z if state is not None else float("nan"))
        if hover_z is None:
            info("拒绝 E3/E4 局部目标: 当前稳定 hover 高度无效")
            return None
        if z is not None:
            try:
                requested_z = float(z)
            except (TypeError, ValueError, OverflowError):
                return None
            if (not math.isfinite(requested_z) or
                    abs(requested_z - hover_z) > 1.0e-6):
                info("拒绝 E3/E4 局部目标: 请求 z 未通过当前 hover 准入")
                return None

        candidate = select_local_safe_goal(
            p0, obstacles, hover_z, required_clearance=clearance,
            occupancy_grid=occupancy_grid)
        if candidate is not None:
            info("选择基于同步障碍+occupancy_grid证据的局部安全目标 "
                 "(%.2f,%.2f,%.2f)" %
                 candidate)
        else:
            info("拒绝 E3/E4 局部目标: 观测支持范围内没有严格净空候选")
        return candidate

    def pick_e1_opposite_goal(self, p0, anchor):
        """Select a fresh-evidence, terminal-safe goal beyond the anchor.

        The direct origin→goal segment still contains the selected obstacle,
        preserving the real bypass requirement.  Only the terminal point is
        admitted against the current synchronized obstacle snapshot; a stale
        or mismatched snapshot fails closed before a FollowTrajectory goal is
        sent.
        """
        obstacles, reasons = self._admitted_obstacle_snapshot()
        if obstacles is None:
            info("拒绝 E1 目标: /uav_state 与 /obstacles 未通过同步准入 (%s)" %
                 ",".join(reasons) if reasons else "unknown")
            return None
        fields = []
        for obstacle in obstacles:
            fields.append((obstacle.center_x, obstacle.center_y,
                           obstacle.size_x, obstacle.size_y))
        selected = select_e1_opposite_goal(p0, anchor, fields)
        if selected is None:
            info("拒绝 E1 目标: 当前障碍证据没有对侧终点净空 %.2fm" %
                 E1_REQUIRED_CLEARANCE_M)
            return None
        gx, gy, terminal_clearance, offset = selected
        state = self.snap()
        goal_z = admitted_hover_altitude(
            state.position_z if state is not None else float("nan"))
        if goal_z is None:
            info("拒绝 E1 目标: 当前 hover 高度无效或偏离 %.2fm" % 1.5)
            return None
        info("E1 对侧终点由新鲜障碍证据准入: (%.2f,%.2f,%.2f), "
             "anchor offset=%.2fm terminal clearance=%.2fm" %
             (gx, gy, goal_z, offset, terminal_clearance))
        return gx, gy, goal_z

    # ------------------------------------------------ 工具

    @staticmethod
    def _wait_future(fut, timeout_s):
        t0 = time.monotonic()
        while not fut.done():
            if time.monotonic() - t0 > timeout_s:
                return None
            time.sleep(0.05)
        return fut.result()

    def _result_future(self, gh):
        """Return one cached result future for a goal handle."""
        if gh is None:
            return None
        key = id(gh)
        future = self._result_futures.get(key)
        if future is None:
            try:
                future = gh.get_result_async()
            except Exception:  # noqa: BLE001
                return None
            self._result_futures[key] = future
        return future

    def follow_goal_is_active(self, gh):
        """Fail closed unless FollowTrajectory is still active.

        rclpy exposes the definitive terminal status through the result
        future.  Before that future completes, an accepted goal is still in
        the normal ACCEPTED/EXECUTING interval.  Once complete, only those
        explicit active statuses pass; E4/E3 therefore cannot issue RTL or
        kill ``traj_server`` after a goal already succeeded/aborted.
        """
        if gh is None or not bool(getattr(gh, "accepted", False)):
            return False
        future = self._result_future(gh)
        if future is None:
            return False
        try:
            if not future.done():
                return goal_is_active(True, False, None)
            wrapped = future.result()
            status = getattr(wrapped, "status", None)
            return goal_is_active(True, True, status, (
                GoalStatus.STATUS_ACCEPTED, GoalStatus.STATUS_EXECUTING))
        except Exception:  # noqa: BLE001
            return False

    def follow_goal_status_diagnostic(self, gh):
        """Return a best-effort status string for event-boundary evidence."""
        if gh is None or not bool(getattr(gh, "accepted", False)):
            return "NONACTIVE_HANDLE"
        future = self._result_future(gh)
        if future is None:
            return "RESULT_FUTURE_UNAVAILABLE"
        try:
            if not future.done():
                return "ACCEPTED_OR_EXECUTING(result_pending)"
            wrapped = future.result()
            status = getattr(wrapped, "status", None)
            return GSTATUS.get(status, "STATUS_%s" % status)
        except Exception as exc:  # noqa: BLE001
            return "RESULT_ERROR:%s" % type(exc).__name__

    def send_goal(self, client, goal, accept_timeout=30.0):
        if not client.wait_for_server(15.0):
            return None
        gh = self._wait_future(client.send_goal_async(goal), accept_timeout)
        if gh is None or not gh.accepted:
            return None
        # Start the single result future immediately.  Reusing it for both
        # active-state checks and final result avoids racing two independent
        # action queries at the E3/E4 event boundary.
        self._result_future(gh)
        return gh

    def call_action(self, client, goal, result_timeout):
        return self.wait_result(self.send_goal(client, goal), result_timeout)

    def wait_result(self, gh, timeout_s):
        if gh is None:
            return None, None
        future = self._result_future(gh)
        if future is None:
            return None, None
        wrapped = self._wait_future(future, timeout_s)
        if wrapped is None:
            return None, None
        return wrapped.status, wrapped.result

    def publish_ego_goal(self, x, y, z=None):
        if z is None:
            state = self.snap()
            z = admitted_hover_altitude(
                state.position_z if state is not None else float("nan"))
            if z is None:
                raise ValueError("没有当前稳定 hover 高度，拒绝发布 EGO goal")
        if not math.isfinite(float(z)):
            raise ValueError("EGO goal z 非有限")
        m = PoseStamped()
        m.header.stamp = self.get_clock().now().to_msg()
        m.header.frame_id = "odom"
        m.pose.position.x = float(x)
        m.pose.position.y = float(y)
        m.pose.position.z = float(z)
        m.pose.orientation.w = 1.0
        self.pub_goal.publish(m)

    def pick_obstacle(self, min_d=3.0, max_d=9.0, max_size=2.5, sample_s=6.0,
                      min_z_size=0.3):
        """时间累积票选障碍中心 (自锚定; 见 navigate_acceptance 同款)。"""
        st = self.snap()
        if st is None:
            return None
        votes = {}
        t0 = time.monotonic()
        while time.monotonic() - t0 < sample_s:
            with self._lock:
                obs_snap = self.obs
            if obs_snap:
                for o in obs_snap.obstacles:
                    d = math.hypot(o.center_x - st.position_x,
                                   o.center_y - st.position_y)
                    if not (min_d <= d <= max_d):
                        continue
                    if max(o.size_x, o.size_y) > max_size or o.size_z < min_z_size:
                        continue
                    key = (round(o.center_x / 1.5), round(o.center_y / 1.5))
                    cnt, sx, sy = votes.get(key, (0, 0.0, 0.0))
                    votes[key] = (cnt + 1, sx + o.center_x, sy + o.center_y)
            time.sleep(0.2)
        if not votes:
            return None

        def info_of(k):
            c, sx, sy = votes[k]
            return c, sx / c, sy / c
        best = max(votes, key=lambda k: (info_of(k)[0],
                                         -math.hypot(info_of(k)[1], info_of(k)[2])))
        c, cx, cy = info_of(best)
        info("选定锚定障碍 (%.2f,%.2f) 票数 %d/%d" % (cx, cy, c, len(votes)))
        return (cx, cy)

    # ------------------------------------------------ 用例

    def wait_ready(self, timeout_s=120.0):
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout_s:
            s = self.snap()
            if s is not None and s.flight_mode != 99 and math.isfinite(s.position_x):
                break
            time.sleep(0.5)
        for c, name in ((self.ac_takeoff, "/takeoff"),
                        (self.ac_follow, "/follow_trajectory")):
            if not c.wait_for_server(30.0):
                raise RuntimeError("action server 不可用: %s" % name)
        if not self.cli_mode.wait_for_service(15.0):
            raise RuntimeError("/set_flight_mode 不可用")
        info("等待 EKF 收敛 (30s)...")
        time.sleep(30.0)

    def takeoff(self, alt=1.5):
        st = None
        for _ in range(3):
            g = Takeoff.Goal()
            g.target_altitude = alt
            g.climb_speed = 1.0
            st, res = self.call_action(self.ac_takeoff, g, 120.0)
            if st == GoalStatus.STATUS_SUCCEEDED:
                break
            if res and "arm failed" in res.message:
                info("arm 失败, 等 20s 重发...")
                time.sleep(20.0)
            else:
                break
        return st == GoalStatus.STATUS_SUCCEEDED

    def ensure_hover(self, alt=1.5):
        """确保机体处于 HOVER (FollowTrajectory 的唯一进入条件)。"""
        s = self.snap()
        if s is not None and s.armed and s.flight_mode == 3:
            return True
        # RTL/降落中: 等落地 disarm
        deadline = time.monotonic() + 150.0
        while time.monotonic() < deadline:
            s = self.snap()
            if s is not None and not s.armed:
                break
            time.sleep(1.0)
        time.sleep(3.0)
        return self.takeoff(alt)

    def wait_for_stable_hover_and_admission(self, hold_s=0.5, timeout_s=30.0):
        """Require stable hover and one continuously fresh state/obstacle/grid set.

        E3/E4 start a new action only after the recovery window is genuinely
        settled.  This prevents a just-recovered emergency-stop ID from being
        mistaken for the requested goal trajectory while old cloud evidence is
        still being replaced.
        """
        start = time.monotonic()
        deadline = start + timeout_s
        next_progress = start + 5.0
        stable_since = None
        reason_counts = Counter()
        last_state = None
        last_speed = float("nan")
        while time.monotonic() < deadline:
            state = self.snap()
            obstacles, occupancy_grid, admission_reasons = \
                self._admitted_local_goal_snapshot()
            last_state = state
            if admission_reasons:
                reason_counts.update(str(reason) for reason in admission_reasons)
            elif obstacles is None or occupancy_grid is None:
                reason_counts["three_source_admission_unavailable"] += 1
            speed = float("nan")
            if state is not None:
                values = (state.velocity_x, state.velocity_y, state.velocity_z)
                if all(math.isfinite(float(value)) for value in values):
                    speed = math.sqrt(sum(float(value) ** 2 for value in values))
                else:
                    reason_counts["velocity_nonfinite"] += 1
            else:
                reason_counts["state_missing"] += 1
            last_speed = speed
            stable = (state is not None and state.armed and state.flight_mode == 3 and
                      state.connected and state.pose_valid and state.velocity_valid and
                      math.isfinite(speed) and speed <= 0.1 and
                      obstacles is not None and occupancy_grid is not None)
            if state is not None:
                if not state.armed:
                    reason_counts["not_armed"] += 1
                if state.flight_mode != 3:
                    reason_counts["not_hover_mode"] += 1
                if not state.connected:
                    reason_counts["state_disconnected"] += 1
                if not state.pose_valid:
                    reason_counts["pose_invalid"] += 1
                if not state.velocity_valid:
                    reason_counts["velocity_invalid"] += 1
                if math.isfinite(speed) and speed > 0.1:
                    reason_counts["speed_above_0.1"] += 1
                elif not math.isfinite(speed):
                    reason_counts["speed_nonfinite"] += 1
            if stable:
                if stable_since is None:
                    stable_since = time.monotonic()
                if time.monotonic() - stable_since >= hold_s:
                    return True
            else:
                stable_since = None
            now = time.monotonic()
            if now >= next_progress:
                pose = (
                    (float(state.position_x), float(state.position_y),
                     float(state.position_z))
                    if state is not None else None)
                info("等待稳定 HOVER/三源 fresh: elapsed=%.1fs/%.1fs "
                     "speed=%.3fm/s pose=%s reasons=%s" %
                     (now - start, timeout_s, speed,
                      pose if pose is not None else "unavailable",
                      ",".join("%s=%d" % item
                               for item in sorted(reason_counts.items())) or
                      "none"))
                while next_progress <= now:
                    next_progress += 5.0
            time.sleep(0.05)
        pose = (
            (float(last_state.position_x), float(last_state.position_y),
             float(last_state.position_z))
            if last_state is not None else None)
        info("稳定 HOVER/三源 fresh 等待超时: timeout=%.1fs hold=%.1fs "
             "speed_limit=0.100m/s last_speed=%.3fm/s last_pose=%s reasons=%s" %
             (timeout_s, hold_s, last_speed,
              pose if pose is not None else "unavailable",
              ",".join("%s=%d" % item
                       for item in sorted(reason_counts.items())) or "none"))
        return False

    def e1_static_avoid(self):
        takeoff_ok = self.takeoff(1.5)
        check("E1 起飞 SUCCEEDED", takeoff_ok)
        if not takeoff_ok:
            return False
        time.sleep(8.0)   # 栅格/雷达稳定
        obst = self.pick_obstacle()
        check("E1 自锚定立柱", obst is not None, "-" if obst else "无锚定障碍")
        if obst is None:
            return False
        self.pillar = obst
        st = self.snap()
        if st is None:
            check("E1 当前 HOVER 状态", False, "无 /uav_state")
            return False
        goal = self.pick_e1_opposite_goal(
            (st.position_x, st.position_y), obst)
        check("E1 新鲜证据下对侧终点安全且仍需绕柱", goal is not None)
        if goal is None:
            return False
        gx, gy, goal_z = goal
        info("锚定立柱 (%.2f,%.2f) → 对侧目标 (%.2f,%.2f,%.2f)" %
             (obst[0], obst[1], gx, gy, goal_z))

        # 顺序关键: 先 follow (等首帧), 再 EGO goal (从机体当前点起规划, 无残留轨迹跳变)
        fg = FollowTrajectory.Goal()
        fg.target_x, fg.target_y, fg.target_z = gx, gy, goal_z
        fg.acceptance_radius = 0.8
        fg.timeout = 90.0
        gh = self.send_goal(self.ac_follow, fg)
        check("E1 follow goal 被接受 (HOVER 进入)", gh is not None)
        if gh is None:
            return False
        time.sleep(0.3)
        baseline_count, baseline_id = self.position_cmd_snapshot()
        action_start = time.monotonic()
        self.publish_ego_goal(gx, gy, goal_z)

        st, res = self.wait_result(gh, 120.0)
        follow_ok = st == GoalStatus.STATUS_SUCCEEDED
        check("E1 FollowTrajectory SUCCEEDED", follow_ok,
              "status=%s msg=%s" % (GSTATUS.get(st, st), res.message if res else "-"))
        trajectory_start, trajectory_id = self.first_new_trajectory_after(
            action_start, baseline_count, baseline_id)
        closest = self.closest_sample_to_point(action_start, obst[0], obst[1])
        min_d = closest[0] if closest is not None else float("nan")
        clearance_ok = min_d > 0.8
        max_z = self.max_sample_z_since(action_start)
        height_ok = e1_pose_height_within_policy(max_z)
        height_detail = (
            "max_z=%.2fm ceiling=%.2fm tolerance=%.2fm" %
            (max_z, E1_MAX_PLANNER_ALTITUDE_M,
             E1_MAX_POSE_ALTITUDE_TOLERANCE_M))
        check("E1 轨迹保持柱顶下方固定高度", height_ok, height_detail)
        action_elapsed = max(0.0, time.monotonic() - action_start)
        if trajectory_start is None:
            trajectory_progress = (
                "trajectory_t unavailable (no new READY /position_cmd; "
                "trajectory_duration unavailable)")
        else:
            trajectory_progress = (
                "trajectory_id=%d trajectory_t=%.2fs; trajectory_duration "
                "unavailable to this acceptance node (progress ratio=NA)" %
                (trajectory_id,
                 max(0.0, (closest[1] - trajectory_start)
                     if closest is not None else 0.0)))
        if closest is None:
            clearance_detail = (
                "无 goal 后位姿样本; action_elapsed=%.2fs; %s" %
                (action_elapsed, trajectory_progress))
        else:
            _, sample_t, sample_x, sample_y, sample_z = closest
            clearance_detail = (
                "最小 %.2fm @ (%.2f,%.2f,%.2f), action_t+%.2fs; "
                "action_elapsed=%.2fs; %s" %
                (min_d, sample_x, sample_y, sample_z,
                 sample_t - action_start, action_elapsed, trajectory_progress))
        check("E1 与立柱 min 距离 >0.8m", clearance_ok, clearance_detail)
        p = self.last_pos()
        err = math.hypot(p[0] - gx, p[1] - gy) if p else float("nan")
        goal_ok = err < 1.0
        check("E1 落点误差 <1.0m", goal_ok, "误差 %.2fm" % err)
        return follow_ok and clearance_ok and height_ok and goal_ok

    def e2_dynamic(self):
        """patrol 行人横穿航线: EGO 在线重规划、与障碍中心 min >0.8m、仍到达。

        锚定方式: 复用 E1 的立柱锚定 + 场景相对几何 (patrol 行人 gazebo 沿
        y=-2, x 14→22; 立柱在 (5,-2) → 巡逻段 = 立柱 + (9..17, 0))。
        原因 (Q22): 行人 1.7m, 14-22m 距离下雷达几乎不可见 → 无法直接锚定,
        只能借立柱相对定位。飞行中记录与 /obstacles 各簇的最小距离。
        """
        if not self.ensure_hover():
            check("E2 就绪 (HOVER)", False, "起飞失败")
            return False
        if self.pillar is None:
            self.pillar = self.pick_obstacle()
        check("E2 锚定立柱 (定位巡逻段)", self.pillar is not None)
        if self.pillar is None:
            return False
        # 目标位于巡逻端点之外 3m（立柱 + 20m），避免把移动物体的工作区
        # 末端选成 terminal point；完整 x=14..22 巡逻段和 >0.8m 净空门不变。
        px, py = self.pillar
        gx = px + E2_PATROL_END_OFFSET_M + E2_GOAL_CLEARANCE_BEYOND_PATROL_M
        gy = py
        st = self.snap()
        goal_z = admitted_hover_altitude(
            st.position_z if st is not None else float("nan"))
        check("E2 目标高度保持稳定 hover", goal_z is not None,
              "当前 z=%.2f" % (st.position_z if st is not None else float("nan")))
        if goal_z is None:
            return False
        info("E2 目标 (%.2f,%.2f) 穿过巡逻段 (立柱+(9..17,0)) 后保持 %.1fm 终点净空" %
             (gx, gy, E2_GOAL_CLEARANCE_BEYOND_PATROL_M))

        fg = FollowTrajectory.Goal()
        fg.target_x, fg.target_y, fg.target_z = gx, gy, goal_z
        fg.acceptance_radius = 0.8
        fg.timeout = 90.0
        gh = self.send_goal(self.ac_follow, fg)
        check("E2 follow goal 被接受", gh is not None)
        if gh is None:
            return False
        time.sleep(0.3)
        self.publish_ego_goal(gx, gy, goal_z)

        # 飞行中记录与所有簇的最小距离 (含动态行人靠近时的观测)。除了保留
        # 原有的硬断言数值，还记录产生最小值的飞行器样本和障碍框快照。
        # 这样可以区分真实近距离穿越、滑窗/消息时延，以及“当前位姿与旧框
        # 中心”错配；诊断信息不改变 0.8m 门槛。
        t_start = time.monotonic()
        min_clear = float("inf")
        min_clear_detail = None
        filter_counts = Counter()
        while time.monotonic() - t_start < 100.0:
            with self._lock:
                o = self.obs
                state = self.state
                state_diag = dict(self.last_state_diag or {})
                obs_diag = dict(self.last_obs_diag or {})
            p = ((state.position_x, state.position_y, state.position_z)
                 if state is not None else None)
            if state is None:
                filter_counts["state_missing"] += 1
            if o is None:
                filter_counts["obstacles_missing"] += 1
            if o is not None and p is not None:
                # State and obstacles are admitted as one evidence pair.  A
                # valid-looking obstacle message cannot pass by itself when
                # the UAV state is stale, disconnected, invalid, or from a
                # different clock/frame.  Invalid evidence is counted so a
                # no-sample failure is actionable rather than a silent pass.
                state_fields = {
                    "connected": bool(state.connected),
                    "pose_valid": bool(state.pose_valid),
                    "position_x": p[0],
                    "position_y": p[1],
                    "position_z": p[2],
                }
                current_ros = self._node_ros_snapshot()
                admitted, reasons = admit_e2_pair(
                    state_fields, state_diag, obs_diag, time.monotonic(),
                    now_ros_ns=current_ros.get("node_ros_ns"))
                if not admitted:
                    for reason in reasons:
                        filter_counts[reason] += 1
                else:
                    filter_counts["accepted_pairs"] += 1
                    if not o.obstacles:
                        filter_counts["empty_obstacles"] += 1
                    for q in o.obstacles:
                        values = (p[0], p[1], p[2], q.center_x, q.center_y,
                                  q.center_z, q.size_x, q.size_y, q.size_z)
                        if not all(math.isfinite(float(value))
                                   for value in values):
                            filter_counts["nonfinite_geometry"] += 1
                            continue
                        filter_counts["clearance_samples"] += 1
                        distance = math.hypot(p[0] - q.center_x,
                                              p[1] - q.center_y)
                        if distance < min_clear:
                            min_clear = distance
                            min_clear_detail = (
                                time.monotonic(), p[0], p[1], p[2],
                                q.center_x, q.center_y, q.center_z,
                                q.size_x, q.size_y, q.size_z,
                                q.obstacle_id, bool(q.is_dynamic),
                                q.velocity_x, q.velocity_y, q.velocity_z,
                                state_diag, obs_diag)
            stt = self.snap()
            if stt is None:
                break
            if math.hypot(stt.position_x - gx, stt.position_y - gy) < 0.8:
                time.sleep(2.0)
                break
            time.sleep(0.3)
        st, res = self.wait_result(gh, 60.0)
        check("E2 FollowTrajectory SUCCEEDED", st == GoalStatus.STATUS_SUCCEEDED,
              "status=%s msg=%s" % (GSTATUS.get(st, st), res.message if res else "-"))
        failure_clock = self._node_ros_snapshot()
        with self._lock:
            last_state_diag = dict(self.last_state_diag or {})
            last_obs_diag = dict(self.last_obs_diag or {})
        filter_text = ", ".join(
            "%s=%d" % (key, value)
            for key, value in sorted(filter_counts.items())) or "none"
        admission_text = (
            "admission: frame=odom, message_age<=%.1fs, future_tolerance=%.1fs, "
            "arrival_age<=%.1fs, same_clock, clock_mismatch filtered; filters={%s}" %
            (E2_MAX_MESSAGE_AGE_S, E2_FUTURE_TOLERANCE_S,
             E2_MAX_ARRIVAL_AGE_S, filter_text))
        if min_clear_detail is None:
            clearance_detail = (
                "无可用障碍框诊断样本; current_node_ros=%.9f clock=%s; "
                "last_uav[%s]; last_obstacles[%s]; %s" %
                (failure_clock.get("node_ros", float("nan")),
                 failure_clock.get("clock_type", "unknown"),
                 self._format_message_diag(last_state_diag),
                 self._format_message_diag(last_obs_diag), admission_text))
        else:
            (sample_t, sample_x, sample_y, sample_z,
             obstacle_x, obstacle_y, obstacle_z,
             obstacle_sx, obstacle_sy, obstacle_sz,
             obstacle_id, obstacle_dynamic, obstacle_vx, obstacle_vy,
             obstacle_vz, state_diag, obs_diag) = min_clear_detail
            clearance_detail = (
                "最小 %.2fm; pose=(%.2f,%.2f,%.2f) t+%.2fs; "
                "obstacle[%d]=(%.2f,%.2f,%.2f) size=(%.2f,%.2f,%.2f) "
                "dynamic=%d velocity=(%.2f,%.2f,%.2f); "
                "current_node_ros=%.9f clock=%s; uav[%s]; obstacles[%s]; %s" %
                (min_clear, sample_x, sample_y, sample_z,
                 sample_t - t_start, obstacle_id,
                 obstacle_x, obstacle_y, obstacle_z,
                 obstacle_sx, obstacle_sy, obstacle_sz,
                 1 if obstacle_dynamic else 0,
                 obstacle_vx, obstacle_vy, obstacle_vz,
                 failure_clock.get("node_ros", float("nan")),
                 failure_clock.get("clock_type", "unknown"),
                 self._format_message_diag(state_diag),
                 self._format_message_diag(obs_diag), admission_text))
        clearance_ok = min_clear_detail is not None and min_clear > 0.8
        check("E2 与障碍 min 距离 >0.8m", clearance_ok, clearance_detail)
        p = self.last_pos()
        err = math.hypot(p[0] - gx, p[1] - gy) if p else float("nan")
        goal_ok = err < 1.0
        check("E2 落点误差 <1.0m", goal_ok, "误差 %.2fm" % err)
        follow_ok = st == GoalStatus.STATUS_SUCCEEDED
        return follow_ok and clearance_ok and goal_ok

    def e4_takeover(self):
        if not self.ensure_hover():
            check("E4 就绪 (HOVER)", False, "起飞失败")
            return False
        if not self.wait_for_stable_hover_and_admission():
            check("E4 就绪 (稳定 HOVER + 三源新鲜证据)", False,
                  "低速/odom/obstacles/occupancy_grid 证据未连续满足 0.5s")
            return False
        st = self.snap()
        p0 = (st.position_x, st.position_y, st.position_z)
        candidate = self.pick_local_safe_goal(p0)
        candidate_detail = (
            "candidate=(%.2f,%.2f,%.2f)" % candidate
            if candidate is not None else "无可验证的局部安全候选")
        check("E4 基于同步 /obstacles+/occupancy_grid 选择局部安全目标",
              candidate is not None,
              candidate_detail)
        if candidate is None:
            return False
        fg = FollowTrajectory.Goal()
        fg.target_x, fg.target_y, fg.target_z = candidate
        fg.acceptance_radius = 0.8
        fg.timeout = 60.0
        gh = self.send_goal(self.ac_follow, fg)
        check("E4 follow goal 被接受", gh is not None)
        if gh is None:
            return False
        time.sleep(0.3)
        baseline_count, baseline_id = self.position_cmd_snapshot()
        self.publish_ego_goal(*candidate)
        trajectory_id = self.wait_for_new_trajectory(
            baseline_count, baseline_id, timeout_s=8.0, origin=p0, target=candidate)
        started = trajectory_id is not None
        check("E4 EGO 新轨迹 /position_cmd 实际启动", started,
              ("trajectory_id=%d" % trajectory_id) if started else
              "未观察到新的 READY trajectory_id (不进入 RTL 接管判定)")
        if not started:
            self.cancel_goal(gh)
            return False
        # wait_for_new_trajectory already requires a new READY command with
        # >=0.25m goal-directed progress.  Keep the action active for the
        # takeover instead of sleeping long enough for a short goal to arrive.
        time.sleep(0.5)
        active = self.follow_goal_is_active(gh)
        check("E4 RTL 前 FollowTrajectory 仍 ACTIVE/ACCEPTED/EXECUTING",
              active, "不触发 RTL" if not active else "goal result 未完成")
        if not active:
            return False
        info("E4 RTL 事件前 action 状态: %s" %
             self.follow_goal_status_diagnostic(gh))
        # 切 RTL (外部接管)
        req = SetFlightMode.Request()
        req.flight_mode = 6
        fut = self.cli_mode.call_async(req)
        self._wait_future(fut, 10.0)
        info("E4 RTL 事件后 action 状态: %s" %
             self.follow_goal_status_diagnostic(gh))
        st, res = self.wait_result(gh, 30.0)
        ok = st == GoalStatus.STATUS_ABORTED and res is not None and \
            "takeover" in res.message
        check("E4 外部接管 → follow abort(takeover)", ok,
              "status=%s msg=%s" % (GSTATUS.get(st, st), res.message if res else "-"))
        return ok

    def e3_stream_cut(self):
        # E4 的 RTL 之后必须先完成独立的 HOVER/重新起飞恢复；main() 只在
        # E4 成功且恢复成功后调用本用例，避免在 RTL 切换窗口级联假故障。
        if not self.ensure_hover():
            check("E3 就绪 (HOVER)", False, "起飞失败")
            return False
        if not self.wait_for_stable_hover_and_admission():
            check("E3 就绪 (稳定 HOVER + 三源新鲜证据)", False,
                  "低速/odom/obstacles/occupancy_grid 证据未连续满足 0.5s")
            return False
        st = self.snap()
        p0 = (st.position_x, st.position_y, st.position_z)
        candidate = self.pick_local_safe_goal(p0)
        candidate_detail = (
            "candidate=(%.2f,%.2f,%.2f)" % candidate
            if candidate is not None else "无可验证的局部安全候选")
        check("E3 基于同步 /obstacles+/occupancy_grid 选择局部安全目标",
              candidate is not None,
              candidate_detail)
        if candidate is None:
            return False
        fg = FollowTrajectory.Goal()
        fg.target_x, fg.target_y, fg.target_z = candidate
        fg.acceptance_radius = 0.8
        fg.timeout = 90.0
        gh = self.send_goal(self.ac_follow, fg)
        check("E3 follow goal 被接受", gh is not None)
        if gh is None:
            return False
        time.sleep(0.3)
        baseline_count, baseline_id = self.position_cmd_snapshot()
        self.publish_ego_goal(*candidate)
        trajectory_id = self.wait_for_new_trajectory(
            baseline_count, baseline_id, timeout_s=8.0, origin=p0, target=candidate)
        started = trajectory_id is not None
        check("E3 EGO 新轨迹 /position_cmd 实际启动", started,
              ("trajectory_id=%d" % trajectory_id) if started else
              "未观察到新的 READY trajectory_id (不杀 traj_server)")
        if not started:
            self.cancel_goal(gh)
            return False
        # READY/进展门只证明此前启动过轨迹, 不保证 kill 当刻任务仍活跃:
        # 若 action 在 kill 前已自然断流并返回 ABORTED(stream_lost), 旧结果
        # 会被归因于后续 kill 而假通过。因此 kill 前做非阻塞 active 检查 —
        # follow_goal_is_active 读取 send_goal 时已缓存的 result future,
        # 对未完成结果不等待, 不是会引入额外网络等待的状态查询; 检查与
        # kill 之间不插入 sleep/等待/网络查询 (局部目标 ~3.3m, 轨迹 2-3s
        # 即完成, 任何 settle 窗口都会自击败)。
        z_before = self.snap().position_z
        active = self.follow_goal_is_active(gh)
        check("E3 kill 前 FollowTrajectory 仍 ACTIVE/ACCEPTED/EXECUTING",
              active, "action 已结束, 不注入故障" if not active else "-")
        if not active:
            info("E3 kill 前 action 状态: %s" %
                 self.follow_goal_status_diagnostic(gh))
            return False
        # 杀 traj_server → /position_cmd 断流
        subprocess.run(["pkill", "-9", "-f", "traj_server"], check=False)
        t_cut = time.monotonic()
        info("E3 kill 事件后 action 状态: %s" %
             self.follow_goal_status_diagnostic(gh))
        st, res = self.wait_result(gh, 20.0)
        dt = time.monotonic() - t_cut
        ok = st == GoalStatus.STATUS_ABORTED and res is not None and \
            res.message == "stream_lost"
        check("E3 断流 → abort(stream_lost) 且 <1.5s", ok and dt < 1.5,
              "status=%s msg=%s (%.2fs)" % (GSTATUS.get(st, st),
                                            res.message if res else "-", dt))
        time.sleep(3.0)
        s = self.snap()
        check("E3 断流后就地悬停 (z 保持, 不坠)", s is not None and s.armed and
              s.flight_mode == 3 and abs(s.position_z - z_before) < 1.2,
              "z=%.2f (断流前 %.2f) mode=%d" %
              (s.position_z if s else float("nan"), z_before,
               s.flight_mode if s else -1))
        return ok


RESULTS = []


def check(name, ok, detail="-"):
    print("  [%s] %s   (%s)" % ("PASS" if ok else "FAIL", name, detail), flush=True)
    RESULTS.append((name, ok))


def info(msg):
    print("  %s" % msg, flush=True)


def run_case(node, title, fn):
    print("\n== %s ==" % title, flush=True)
    t0 = time.monotonic()
    try:
        outcome = fn()
        ok = outcome is not False
        if not ok:
            RESULTS.append((title, False))
    except Exception as e:  # noqa: BLE001
        print("  [FAIL] %s 异常: %s" % (title, e), flush=True)
        RESULTS.append((title, False))
        ok = False
    print("  -- %s 用时 %.0fs --" % (title, time.monotonic() - t0), flush=True)
    return ok


def main():
    rclpy.init()
    node = EgoAcceptance()
    ex = MultiThreadedExecutor(num_threads=4)
    ex.add_node(node)
    threading.Thread(target=ex.spin, daemon=True).start()

    print("=" * 60)
    print("EasyFly M4.3 EGO-Planner 集成验收 (轻链)")
    print("=" * 60)

    run_case(node, "就绪检查", node.wait_ready)
    e1_ok = run_case(node, "E1 静态绕障", node.e1_static_avoid)
    if e1_ok:
        run_case(node, "E2 动态重规划", node.e2_dynamic)
    else:
        # E2 reuses E1's anchor and assumes the vehicle ended in a valid
        # hover.  Recover first, then record an explicit dependency skip; do
        # not manufacture a second failure from E1's unsafe state.
        e1_recovered = run_case(node, "E1 后恢复 HOVER/重新起飞", node.ensure_hover)
        reason = ("E1 失败，恢复成功后跳过" if e1_recovered else
                  "E1 失败且恢复未完成，跳过")
        info("E2 跳过：%s，避免依赖级联" % reason)
        RESULTS.append(("E2 跳过（依赖 E1 失败）", False))

    # E4 deliberately enters RTL.  Always attempt to restore a known HOVER
    # state, but never start E3 while E4 is failed or recovery is incomplete:
    # doing so turns one takeover timing failure into a misleading stream-loss
    # cascade and may issue a new goal while PX4 is still in RTL.
    e4_ok = run_case(node, "E4 接管让位", node.e4_takeover)
    recovered = run_case(node, "E4 后恢复 HOVER/重新起飞", node.ensure_hover)
    if e4_ok and recovered:
        run_case(node, "E3 流中断安全", node.e3_stream_cut)
    else:
        info("E3 跳过：E4 未通过或机体尚未恢复 HOVER，避免在 RTL 窗口级联")
        RESULTS.append(("E3 跳过（E4/恢复失败）", False))

    print("\n" + "=" * 60)
    failed = sum(1 for _, ok in RESULTS if not ok)
    for n, ok in RESULTS:
        print("  %s  %s" % ("PASS" if ok else "FAIL", n))
    print("=" * 60)
    ex.shutdown()
    rclpy.shutdown()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
