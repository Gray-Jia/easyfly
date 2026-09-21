#!/usr/bin/env python3
"""
navigate_acceptance.py — M4.2 全局规划验收

用例:
  N1  就绪        /occupancy_grid + /uav_state + action server
  N2  绕障导航     hover → 自锚定障碍后方目标: 必须 SUCCEEDED + 全程不进入
                   该障碍膨胀 AABB + 落点误差 <1.0m
  N3  返程导航     /navigate (1,0) → SUCCEEDED + 落点误差 <1.0m
  N5  目标在障碍内 → ABORTED (goal in obstacle)
  N4  取消语义     发起远距导航后 cancel → CANCELED + 悬停空中

  执行顺序: N1→N2→N3→N5→N4 (N4 为末位飞行用例)

前置: run_navigate_acceptance.sh 已启动 perception_sitl。
退出码: 0=全部通过
"""

import math
import sys
import threading
import time
from dataclasses import dataclass

import rclpy
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile

from action_msgs.msg import GoalStatus
from easyfly_msgs.action import GoToWaypoint, NavigateTo, Takeoff
from easyfly_msgs.msg import ObstacleInfoArray, UAVState
from nav_msgs.msg import OccupancyGrid

# min_clearance_to_aabb is the point-compatible name; the trajectory helper
# additionally checks every segment between consecutive UAV samples.
from g7_geometry import (min_trajectory_clearance_to_aabb,
                         obstacle_observation_rejection_reason,
                         update_obstacle_clusters)

GSTATUS = {
    GoalStatus.STATUS_SUCCEEDED: "SUCCEEDED",
    GoalStatus.STATUS_CANCELED: "CANCELED",
    GoalStatus.STATUS_ABORTED: "ABORTED",
}

# MID-360 at the 2.5m flight height often sees only a local pillar slice.
# Keep a positive vertical floor for obstacle identity without requiring the
# unseen full pillar height.
N2_MIN_VISIBLE_HEIGHT = 0.15

# 场景真值 (perception_demo.world): 验收关心的障碍
@dataclass(frozen=True)
class ObstacleCandidate:
    """N2 锚定障碍及其几何尺寸（均在 odom 系）。"""

    center_x: float
    center_y: float
    size_x: float
    size_y: float
    size_z: float
    votes: int

    @property
    def center(self):
        return self.center_x, self.center_y


class NavigateAcceptance(Node):

    def __init__(self):
        super().__init__("navigate_acceptance")
        self._lock = threading.Lock()
        self.grid = None
        self.grid_age_t = None
        self.grid_seq = 0
        self.obs = None
        self.obs_age_t = None
        self.obs_seq = 0
        self.last_obstacle_diagnostic = "尚未执行障碍筛选"
        self.state = None
        self.fb = None
        self._feedback_goal_id = None
        self._feedback_attempt = 0
        self._feedback_callback_active = False
        self.pos_samples = []  # (t, x, y)
        self.create_subscription(OccupancyGrid, "/occupancy_grid",
                                 self._on_grid, QoSProfile(depth=5))
        self.create_subscription(ObstacleInfoArray, "/obstacles",
                                 self._on_obs, QoSProfile(depth=5))
        self.create_subscription(UAVState, "/uav_state",
                                 self._on_state, QoSProfile(depth=10))
        self.create_subscription(NavigateTo.Impl.FeedbackMessage,
                                 "/navigate/_action/feedback",
                                 self._on_fb, QoSProfile(depth=50))
        self.ac_nav = ActionClient(self, NavigateTo, "/navigate")
        self.ac_wp = ActionClient(self, GoToWaypoint, "/goto_waypoint")
        self.ac_takeoff = ActionClient(self, Takeoff, "/takeoff")

    def _on_obs(self, msg):
        with self._lock:
            self.obs = msg
            self.obs_age_t = time.monotonic()
            self.obs_seq += 1

    def _on_grid(self, msg):
        with self._lock:
            self.grid = msg
            self.grid_age_t = time.monotonic()
            self.grid_seq += 1
    def _on_state(self, msg):
        with self._lock:
            self.state = msg
            self.pos_samples.append((time.monotonic(),
                                     msg.position_x, msg.position_y))
            if len(self.pos_samples) > 4000:
                self.pos_samples = self.pos_samples[-2000:]
    def _on_fb(self, msg):
        with self._lock:
            if self._feedback_callback_active:
                return
            if self._feedback_goal_id is None:
                return
            if self._uuid_key(msg.goal_id) != self._feedback_goal_id:
                return
            self.fb = msg.feedback

    @staticmethod
    def _uuid_key(value):
        raw = getattr(value, "uuid", value)
        return bytes(raw)

    def _begin_feedback_attempt(self):
        with self._lock:
            self._feedback_attempt += 1
            token = self._feedback_attempt
            self._feedback_goal_id = None
            self.fb = None
            self._feedback_callback_active = True
            return token

    def _on_goal_feedback(self, token, msg):
        key = self._uuid_key(msg.goal_id)
        with self._lock:
            if token != self._feedback_attempt:
                return
            if self._feedback_goal_id is None:
                self._feedback_goal_id = key
            if key != self._feedback_goal_id:
                return
            self.fb = msg.feedback

    def snap(self):
        with self._lock:
            return self.grid, self.state, self.fb

    def snap_obstacles(self):
        with self._lock:
            return self.obs, self.obs_age_t, self.obs_seq

    def grid_snapshot(self):
        with self._lock:
            return self.grid, self.grid_age_t, self.grid_seq

    def pick_obstacle(self, min_d=3.0, max_d=8.0, max_size=2.5,
                      sample_s=20.0, min_votes=3):
        """只使用本次调用期间到达的新鲜障碍，并返回中心和尺寸。

        聚类输出逐帧波动大 (M4.0 已知), 单帧会撞上稀疏帧。连续采样
        sample_s 秒, 按 0.6m 关联半径给障碍中心投票，且至少需要 min_votes
        个新鲜消息命中同一空间簇。V2-17: 套件开局聚类链有启动期 (首个
        飞行用例约 60-90s 时聚类未就绪), 保留 60s 启动等待和 20s 采样窗，
        不把任意缓存的旧 obstacles 当作 ready。
        """
        warm = time.monotonic()
        _, _, baseline_seq = self.snap_obstacles()
        while time.monotonic() - warm < 60:
            obs, _, seq = self.snap_obstacles()
            if seq > baseline_seq and obs is not None and obs.obstacles:
                break
            time.sleep(1.0)
        _, st, _ = self.snap()
        if st is None or not st.pose_valid:
            self.last_obstacle_diagnostic = "障碍筛选未执行: UAV pose 尚未有效"
            return None
        # 细粒度空间关联：旧版 1.5m round 网格会把相邻独立障碍合并。
        # 同一条消息不能复用 cluster；中心仍做时序平均以抗抖，尺寸取 max
        # 以保守估计膨胀后的 AABB 足迹。
        clusters = []
        filter_stats = {
            "messages": 0,
            "observations": 0,
            "stale": 0,
            "nonfinite": 0,
            "distance": 0,
            "xy_size": 0,
            "visible_height": 0,
            "accepted": 0,
        }
        sample_start = time.monotonic()
        seen_seq = baseline_seq
        while time.monotonic() - sample_start < sample_s:
            obs_snap, arrival_t, seq = self.snap_obstacles()
            if obs_snap and arrival_t is not None and seq > seen_seq:
                seen_seq = seq
                filter_stats["messages"] += 1
                if time.monotonic() - arrival_t > 2.0:
                    filter_stats["stale"] += 1
                    continue
                for o in obs_snap.obstacles:
                    filter_stats["observations"] += 1
                    try:
                        center_z = float(o.center_z)
                    except (TypeError, ValueError):
                        filter_stats["nonfinite"] += 1
                        continue
                    if not math.isfinite(center_z):
                        filter_stats["nonfinite"] += 1
                        continue
                    values = (o.center_x, o.center_y, o.size_x,
                              o.size_y, o.size_z)
                    reason = obstacle_observation_rejection_reason(
                        values, (st.position_x, st.position_y), min_d, max_d,
                        max_size, min_visible_height=N2_MIN_VISIBLE_HEIGHT)
                    if reason is not None:
                        filter_stats[reason] += 1
                        continue
                    filter_stats["accepted"] += 1
                    update_obstacle_clusters(
                        clusters,
                        [values],
                        seen_seq, association_radius=0.6)
            time.sleep(0.2)
        cluster_count = len(clusters)
        clusters = [cluster for cluster in clusters if cluster.count >= min_votes]
        if not clusters:
            self.last_obstacle_diagnostic = (
                "障碍候选为空: 新鲜消息=%d, 观测=%d, 通过=%d, "
                "丢弃(stale=%d nonfinite=%d distance=%d xy=%d height<%.2f=%d), "
                "空间簇=%d, 需要票数=%d" % (
                    filter_stats["messages"], filter_stats["observations"],
                    filter_stats["accepted"], filter_stats["stale"],
                    filter_stats["nonfinite"], filter_stats["distance"],
                    filter_stats["xy_size"], N2_MIN_VISIBLE_HEIGHT,
                    filter_stats["visible_height"],
                    cluster_count, min_votes))
            print("    [调试] %s" % self.last_obstacle_diagnostic, flush=True)
            return None

        # 出现次数最多 (稳定目标), 平票取更近的
        best = max(clusters, key=lambda cluster: (
            cluster.count, -math.hypot(cluster.center_x, cluster.center_y)))
        cnt = best.count
        cx, cy = best.center_x, best.center_y
        size_x, size_y, size_z = (best.max_size_x, best.max_size_y, best.max_size_z)
        print("    [调试] 选定障碍 (%.2f,%.2f) 尺寸(%.2f,%.2f,%.2f) 票数 %d/%d" %
              (cx, cy, size_x, size_y, size_z, cnt, len(clusters)), flush=True)
        self.last_obstacle_diagnostic = (
            "已选障碍: 票数=%d/%d, 通过观测=%d" %
            (cnt, len(clusters), filter_stats["accepted"]))
        return ObstacleCandidate(cx, cy, size_x, size_y, size_z, cnt)

    @staticmethod
    def _wait_future(fut, timeout_s):
        t0 = time.monotonic()
        while not fut.done():
            if time.monotonic() - t0 > timeout_s:
                return None
            time.sleep(0.05)
        return fut.result()

    def call_action(self, client, goal, result_timeout):
        if not client.wait_for_server(10.0):
            return None, None
        if client is self.ac_nav:
            gh = self.send_nav_goal(goal)
        else:
            gh = self._wait_future(client.send_goal_async(goal), 30.0)
        if gh is None or not gh.accepted:
            return "REJECTED", None
        wrapped = self._wait_future(gh.get_result_async(), result_timeout)
        if wrapped is None:
            return None, None
        return wrapped.status, wrapped.result

    def send_nav_goal(self, goal):
        """发送一个 NavigateTo，并把反馈绑定到本次 goal/token。"""
        if not self.ac_nav.wait_for_server(10.0):
            return None
        token = self._begin_feedback_attempt()

        def callback(msg):
            self._on_goal_feedback(token, msg)

        gh = self._wait_future(
            self.ac_nav.send_goal_async(goal, feedback_callback=callback), 30.0)
        if gh is None or not gh.accepted:
            return gh
        with self._lock:
            if token == self._feedback_attempt:
                handle_key = self._uuid_key(gh.goal_id)
                if self._feedback_goal_id != handle_key:
                    self._feedback_goal_id = handle_key
                    self.fb = None
        return gh

    def min_dist_to_point(self, t_start, px, py):
        ds = [math.hypot(x - px, y - py) for t, x, y in self.pos_samples
              if t >= t_start]
        return min(ds) if ds else float("nan")

    def grid_occupied_goal(self, min_seq=0, max_age=2.0, timeout=10.0):
        """等待新鲜栅格后取一个占据格中心，不使用 fallback 旧/未知格。"""
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            grid, age_t, seq = self.grid_snapshot()
            if (grid is not None and age_t is not None and seq > min_seq and
                    time.monotonic() - age_t <= max_age):
                break
            time.sleep(0.2)
        else:
            return None
        res = grid.info.resolution
        ox, oy = grid.info.origin.position.x, grid.info.origin.position.y
        for r in range(grid.info.height):
            for c in range(grid.info.width):
                if grid.data[r * grid.info.width + c] >= 50:
                    wx, wy = ox + (c + 0.5) * res, oy + (r + 0.5) * res
                    d = math.hypot(wx, wy)
                    if 3.0 <= d <= 10.0:
                        return (wx, wy)
        return None

    def grid_is_occupied(self, x, y, max_age=2.0):
        """检查当前新鲜栅格中的目标点，避免 N2 自己构造占据格目标。"""
        grid, age_t, _ = self.grid_snapshot()
        if (grid is None or age_t is None or
                time.monotonic() - age_t > max_age):
            return None
        res = grid.info.resolution
        ox, oy = grid.info.origin.position.x, grid.info.origin.position.y
        col = int(math.floor((x - ox) / res))
        row = int(math.floor((y - oy) / res))
        if not (0 <= col < grid.info.width and 0 <= row < grid.info.height):
            return None
        return grid.data[row * grid.info.width + col] >= 50

    def last_pos(self):
        return (self.pos_samples[-1][1], self.pos_samples[-1][2]
                ) if self.pos_samples else (None, None)


RESULTS = []


def check(name, ok, detail="-"):
    print("  [%s] %s   (%s)" % ("PASS" if ok else "FAIL", name, detail), flush=True)
    RESULTS.append((name, ok))


def info(msg):
    print("  %s" % msg, flush=True)


def _takeoff(alt):
    g = Takeoff.Goal()
    g.target_altitude = alt
    g.climb_speed = 1.0
    return g


def _nav(x, y, z, speed=2.0):
    g = NavigateTo.Goal()
    g.target_x, g.target_y, g.target_z = x, y, z
    g.max_speed = speed
    return g


def main():
    rclpy.init()
    node = None
    ex = None
    spin_thread = None
    try:
        node = NavigateAcceptance()
        ex = MultiThreadedExecutor(num_threads=4)
        ex.add_node(node)
        spin_thread = threading.Thread(target=ex.spin, daemon=True)
        spin_thread.start()


        print("=" * 60)
        print("EasyFly M4.2 全局导航验收")
        print("=" * 60)

        # ---- N1 就绪 ----
        print("\n== N1 就绪检查 ==")
        t0 = time.monotonic()
        while node.snap()[0] is None and time.monotonic() - t0 < 90:
            time.sleep(0.5)
        check("N1 /occupancy_grid 数据流", node.snap()[0] is not None)
        for c, name in ((node.ac_takeoff, "/takeoff"), (node.ac_nav, "/navigate")):
            check("N1 action %s" % name, c.wait_for_server(30.0))
        info("等待 EKF 收敛 (30s)...")
        time.sleep(30)

        # ---- N2 绕障导航 ----
        print("\n== N2 绕障导航 (自锚定: 实测障碍后方目标) ==")
        nav_hover = None
        try:
            st, res = None, None
            for attempt in (1, 2):
                st, res = node.call_action(node.ac_takeoff, _takeoff(2.5), 120.0)
                if st == GoalStatus.STATUS_SUCCEEDED:
                    break
                if attempt == 1 and res and "arm failed" in res.message:
                    info("arm 失败, 等 20s 重发...")
                    time.sleep(20)
            check("N2 起飞 SUCCEEDED", st == GoalStatus.STATUS_SUCCEEDED,
                  "msg=%s" % (res.message if res else "-"))
            time.sleep(8)  # 栅格稳定 (起飞爬升期点云混乱)
            obst = node.pick_obstacle()
            check("N2 找到锚定障碍", obst is not None,
                  "-" if obst else node.last_obstacle_diagnostic)
            if obst is None:
                raise RuntimeError("无锚定障碍")
            nav_hover = node.last_pos()
            # 目标 = 障碍中心沿 无人机→障碍 方向再退 2.5m (视线必穿障碍)
            _, st0, _ = node.snap()
            dx = obst.center_x - st0.position_x
            dy = obst.center_y - st0.position_y
            d = math.hypot(dx, dy)
            gx = obst.center_x + dx / d * 2.5
            gy = obst.center_y + dy / d * 2.5
            info("锚定障碍 (%.2f,%.2f) 尺寸(%.2f,%.2f), 目标 (%.2f,%.2f)" %
                 (obst.center_x, obst.center_y, obst.size_x, obst.size_y, gx, gy))
            goal_occupied = node.grid_is_occupied(gx, gy)
            check("N2 构造目标不在新鲜占据格", goal_occupied is False,
                  "occupied=%s" % goal_occupied)
            if goal_occupied is not False:
                raise RuntimeError("N2 目标栅格不可确认为空闲")
            node.pos_samples.clear()
            t_start = time.monotonic()
            st, res = node.call_action(node.ac_nav, _nav(gx, gy, 2.5), 180.0)
            check("N2 导航 SUCCEEDED", st == GoalStatus.STATUS_SUCCEEDED,
                  "status=%s msg=%s" % (GSTATUS.get(st, st), res.message if res else "-"))
            samples = [(x, y) for t, x, y in node.pos_samples if t >= t_start]
            min_clearance = min_trajectory_clearance_to_aabb(
                samples, obst.center_x, obst.center_y, obst.size_x, obst.size_y, 0.5)
            min_center_dist = node.min_dist_to_point(
                t_start, obst.center_x, obst.center_y)
            check("N2 轨迹与膨胀 AABB 保持安全间距", min_clearance > 0.1,
                  "最小 clearance %.2fm (中心距 %.2fm)" %
                  (min_clearance, min_center_dist))
            _, _, fb = node.snap()
            segs = fb.total_segments if fb else 0
            check("N2 路径多段 (发生绕行)", segs >= 2, "%d 段" % segs)
            x, y = node.last_pos()
            err = math.hypot(x - gx, y - gy) if x is not None else float("nan")
            check("N2 落点误差 <1.0m", err < 1.0, "误差 %.2fm" % err)
        except Exception as e:  # noqa: BLE001
            print("  [FAIL] N2 异常: %s" % e, flush=True)
            RESULTS.append(("N2", False))

        # ---- N3 返程导航 (回到起飞悬停点, 实时坐标无偏移问题) ----
        print("\n== N3 返程导航 ==")
        try:
            if nav_hover is None:
                nav_hover = node.last_pos()
            st, res = node.call_action(
                node.ac_nav, _nav(nav_hover[0], nav_hover[1], 2.5), 180.0)
            check("N3 导航 SUCCEEDED", st == GoalStatus.STATUS_SUCCEEDED,
                  "status=%s msg=%s" % (GSTATUS.get(st, st), res.message if res else "-"))
            x, y = node.last_pos()
            err = math.hypot(x - nav_hover[0], y - nav_hover[1]) if x is not None \
                else float("nan")
            check("N3 落点误差 <1.0m", err < 1.0, "误差 %.2fm" % err)
        except Exception as e:  # noqa: BLE001
            print("  [FAIL] N3 异常: %s" % e, flush=True)
            RESULTS.append(("N3", False))

        # ---- N5 目标在障碍内 (自锚定: 实测障碍中心) ----
        print("\n== N5 目标在障碍内 ==")
        try:
            # goal 直接取本次调用之后到达的新鲜栅格占据格中心 (与 A* 输入同源,
            # 判定不受 EKF 慢漂影响；禁止复用起飞前持久化的旧栅格)。
            _, _, n5_grid_seq = node.grid_snapshot()
            goal = node.grid_occupied_goal(min_seq=n5_grid_seq, max_age=2.0,
                                           timeout=15.0)
            check("N5 找到新鲜占据格", goal is not None)
            if goal is None:
                raise RuntimeError("没有新鲜栅格占据格")
            info("占据格中心 goal: (%.2f, %.2f)" % goal)
            st, res = node.call_action(node.ac_nav, _nav(goal[0], goal[1], 2.5), 60.0)
            ok = (st == GoalStatus.STATUS_ABORTED and res and
                  "obstacle" in res.message)
            check("N5 ABORTED (goal in obstacle)", ok,
                  "status=%s msg=%r" % (GSTATUS.get(st, st), res.message if res else "-"))
        except Exception as e:  # noqa: BLE001
            print("  [FAIL] N5 异常: %s" % e, flush=True)
            RESULTS.append(("N5", False))

        # ---- N4 取消语义 (目标 = 当前位置 + 15m, 方向取障碍质心反向) ----
        print("\n== N4 取消语义 ==")
        try:
            _, st0, _ = node.snap()
            obs_snap, _, _ = node.snap_obstacles()
            if obs_snap and len(obs_snap.obstacles) > 0:
                cx = sum(o.center_x for o in obs_snap.obstacles) / len(obs_snap.obstacles)
                cy = sum(o.center_y for o in obs_snap.obstacles) / len(obs_snap.obstacles)
                dx = st0.position_x - cx
                dy = st0.position_y - cy
                dn = math.hypot(dx, dy) or 1.0
                gx = st0.position_x + dx / dn * 15.0
                gy = st0.position_y + dy / dn * 15.0
            else:
                gx, gy = st0.position_x, st0.position_y + 15.0
            g = _nav(gx, gy, 2.5)
            gh = node.send_nav_goal(g)
            check("N4 导航 goal 被接受", gh is not None and gh.accepted)
            time.sleep(6)  # 飞一段
            cfut = gh.cancel_goal_async()
            node._wait_future(cfut, 10.0)
            wrapped = node._wait_future(gh.get_result_async(), 30.0)
            check("N4 取消后 CANCELED",
                  wrapped is not None and wrapped.status == GoalStatus.STATUS_CANCELED,
                  "status=%s" % (GSTATUS.get(wrapped.status, wrapped.status) if wrapped else "-"))
            time.sleep(3)
            _, state, _ = node.snap()
            check("N4 取消后悬停空中", state is not None and state.armed and state.position_z > 1.0,
                  "z=%.2f armed=%s" % (state.position_z if state else -1,
                                       state.armed if state else "-"))
        except Exception as e:  # noqa: BLE001
            print("  [FAIL] N4 异常: %s" % e, flush=True)
            RESULTS.append(("N4", False))

        print("\n" + "=" * 60)
        failed = sum(1 for _, ok in RESULTS if not ok)
        for n, ok in RESULTS:
            print("  %s  %s" % ("PASS" if ok else "FAIL", n))
        print("=" * 60)
        return 1 if failed else 0
    finally:
        try:
            if ex is not None:
                ex.shutdown()
        finally:
            try:
                if spin_thread is not None:
                    spin_thread.join(timeout=5.0)
            finally:
                try:
                    if node is not None:
                        node.destroy_node()
                finally:
                    if rclpy.ok():
                        rclpy.shutdown()


if __name__ == "__main__":
    sys.exit(main())
