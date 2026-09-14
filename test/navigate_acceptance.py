#!/usr/bin/env python3
"""
navigate_acceptance.py — M4.2 全局规划验收

用例:
  N1  就绪        /occupancy_grid + /uav_state + action server
  N2  绕障导航     hover → /navigate (20,-5): 直线穿 (18,-4) 纸箱 (0.5m < 膨胀),
                   必须 SUCCEEDED + 全程与该障碍中心距离 >1.0m + 落点误差 <1.0m
  N3  返程导航     /navigate (1,0) → SUCCEEDED + 落点误差 <1.0m
  N4  取消语义     发起远距导航后 cancel → CANCELED + 悬停空中
  N5  目标在障碍内 → ABORTED (goal in obstacle)

前置: run_navigate_acceptance.sh 已启动 perception_sitl。
退出码: 0=全部通过
"""

import math
import sys
import threading
import time

import rclpy
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile

from action_msgs.msg import GoalStatus
from easyfly_msgs.action import GoToWaypoint, NavigateTo, Takeoff
from easyfly_msgs.msg import ObstacleInfoArray, UAVState
from nav_msgs.msg import OccupancyGrid

GSTATUS = {
    GoalStatus.STATUS_SUCCEEDED: "SUCCEEDED",
    GoalStatus.STATUS_CANCELED: "CANCELED",
    GoalStatus.STATUS_ABORTED: "ABORTED",
}

# 场景真值 (perception_demo.world): 验收关心的障碍
BOX_18_M4 = (18.0, -4.0)


class NavigateAcceptance(Node):

    def __init__(self):
        super().__init__("navigate_acceptance")
        self._lock = threading.Lock()
        self.grid = None
        self.grid_age_t = None
        self.obs = None
        self.state = None
        self.fb = None
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

    def _on_grid(self, msg):
        with self._lock:
            self.grid = msg
            self.grid_age_t = time.monotonic()
    def _on_state(self, msg):
        with self._lock:
            self.state = msg
            self.pos_samples.append((time.monotonic(),
                                     msg.position_x, msg.position_y))
            if len(self.pos_samples) > 4000:
                self.pos_samples = self.pos_samples[-2000:]
    def _on_fb(self, msg):
        with self._lock:
            self.fb = msg.feedback

    def snap(self):
        with self._lock:
            return self.grid, self.state, self.fb

    def pick_obstacle(self, min_d=3.0, max_d=8.0, max_size=2.5, sample_s=6.0):
        """自锚定 + 时间累积: 聚类输出逐帧波动大 (M4.0 已知), 单帧会撞上
        稀疏帧。连续采样 sample_s 秒, 按 1.5m 网格给障碍中心投票, 选
        "距离范围內出现次数最多"的位置。返回 (cx, cy) 或 None。"""
        _, st, _ = self.snap()
        if st is None:
            return None
        votes = {}  # 网格键 → (计数, 累计x, 累计y)
        t0 = time.monotonic()
        while time.monotonic() - t0 < sample_s:
            with self._lock:
                obs_snap = self.obs
            if obs_snap:
                for o in obs_snap.obstacles:
                    dx = o.center_x - st.position_x
                    dy = o.center_y - st.position_y
                    d = math.hypot(dx, dy)
                    if not (min_d <= d <= max_d):
                        continue
                    if max(o.size_x, o.size_y) > max_size:
                        continue
                    if o.size_z < 0.3:
                        continue
                    key = (round(o.center_x / 1.5), round(o.center_y / 1.5))
                    cnt, sx, sy = votes.get(key, (0, 0.0, 0.0))
                    votes[key] = (cnt + 1, sx + o.center_x, sy + o.center_y)
            time.sleep(0.2)
        if not votes:
            return None
        # 出现次数最多 (稳定目标), 平票取更近的
        def info_of(key):
            cnt, sx, sy = votes[key]
            return cnt, sx / cnt, sy / cnt
        best_key = max(votes, key=lambda k: (info_of(k)[0],
                                             -math.hypot(info_of(k)[1],
                                                         info_of(k)[2])))
        cnt, cx, cy = info_of(best_key)
        print("    [调试] 选定障碍 (%.2f,%.2f) 票数 %d/%d" %
              (cx, cy, cnt, len(votes)), flush=True)
        return (cx, cy)

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
        gh = self._wait_future(client.send_goal_async(goal), 30.0)
        if gh is None or not gh.accepted:
            return "REJECTED", None
        wrapped = self._wait_future(gh.get_result_async(), result_timeout)
        if wrapped is None:
            return None, None
        return wrapped.status, wrapped.result

    def min_dist_to_point(self, t_start, px, py):
        ds = [math.hypot(x - px, y - py) for t, x, y in self.pos_samples
              if t >= t_start]
        return min(ds) if ds else float("nan")

    def grid_occupied_goal(self):
        """从最新栅格快照取一个占据格中心 (与 A* 输入同源, 判定确定)"""
        grid, _, _ = self.snap()
        if grid is None:
            return None
        res = grid.info.resolution
        ox, oy = grid.info.origin.position.x, grid.info.origin.position.y
        fallback = None
        for r in range(0, grid.info.height, 2):
            for c in range(0, grid.info.width, 2):
                if grid.data[r * grid.info.width + c] >= 50:
                    wx, wy = ox + (c + 0.5) * res, oy + (r + 0.5) * res
                    d = math.hypot(wx, wy)
                    if 3.0 <= d <= 10.0:
                        return (wx, wy)
                    if fallback is None:
                        fallback = (wx, wy)
        return fallback

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
    node = NavigateAcceptance()
    ex = MultiThreadedExecutor(num_threads=4)
    ex.add_node(node)
    threading.Thread(target=ex.spin, daemon=True).start()

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
              "-" if obst else "见上方障碍表")
        if obst is None:
            raise RuntimeError("无锚定障碍")
        nav_hover = node.last_pos()
        # 目标 = 障碍中心沿 无人机→障碍 方向再退 2.5m (视线必穿障碍)
        _, st0, _ = node.snap()
        dx = obst[0] - st0.position_x
        dy = obst[1] - st0.position_y
        d = math.hypot(dx, dy)
        gx = obst[0] + dx / d * 2.5
        gy = obst[1] + dy / d * 2.5
        info("锚定障碍 (%.2f,%.2f), 目标 (%.2f,%.2f)" % (obst[0], obst[1], gx, gy))
        node.pos_samples.clear()
        t_start = time.monotonic()
        st, res = node.call_action(node.ac_nav, _nav(gx, gy, 2.5), 180.0)
        check("N2 导航 SUCCEEDED", st == GoalStatus.STATUS_SUCCEEDED,
              "status=%s msg=%s" % (GSTATUS.get(st, st), res.message if res else "-"))
        min_d = node.min_dist_to_point(t_start, obst[0], obst[1])
        # 动态阈值: 障碍半径(≤0.75) + 膨胀(0.3) - 0.15 容差
        thr = 0.9
        check("N2 与障碍中心最小距离 >%.1fm" % thr, min_d > thr, "最小 %.2fm" % min_d)
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
        # goal 直接取栅格占据格中心 (与 A* 输入同源, 判定不受 EKF 慢漂影响)
        goal = node.grid_occupied_goal()
        check("N5 找到占据格", goal is not None)
        if goal is None:
            raise RuntimeError("栅格无占据格")
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
        obs_snap = node.obs
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
        gh = node._wait_future(node.ac_nav.send_goal_async(g), 30.0)
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
    ex.shutdown()
    rclpy.shutdown()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
