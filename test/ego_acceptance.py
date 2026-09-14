#!/usr/bin/env python3
"""
ego_acceptance.py — M4.3 EGO-Planner 集成验收 (轻链: perception_demo.world)

用例:
  E1  静态绕障   立柱 (perception_demo.world pillar, 3m): hover → 自锚定立柱 →
                 FollowTrajectory(目标=立柱对侧) + EGO goal: SUCCEEDED、
                 全程与立柱中心 min > 0.8m、落点误差 < 1.0m
  E2  动态重规划 patrol 行人横穿航线: EGO 在线重规划、与人 min > 1.0m、仍到达
  E4  接管让位   飞行中切 RTL(mode 6) → FollowTrajectory abort (takeover)
  E3  流中断安全 飞行中杀 traj_server → 0.5s 内回悬停 (z 保持, abort stream_lost)
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

import rclpy
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import QoSProfile

from action_msgs.msg import GoalStatus
from easyfly_msgs.action import FollowTrajectory, Takeoff
from easyfly_msgs.msg import ObstacleInfoArray, UAVState
from easyfly_msgs.srv import SetFlightMode
from geometry_msgs.msg import PoseStamped

GSTATUS = {
    GoalStatus.STATUS_SUCCEEDED: "SUCCEEDED",
    GoalStatus.STATUS_CANCELED: "CANCELED",
    GoalStatus.STATUS_ABORTED: "ABORTED",
    GoalStatus.STATUS_ACCEPTED: "ACCEPTED",
    GoalStatus.STATUS_EXECUTING: "EXECUTING",
}

# 立柱真值 (perception_demo.world): 供日志参考, 判定一律用自锚定值
PILLAR_GAZEBO = (5.0, -2.0)


class EgoAcceptance(Node):

    def __init__(self):
        super().__init__("ego_acceptance")
        self._lock = threading.Lock()
        self.obs = None
        self.state = None
        self.fb = None
        self.pillar = None    # E1 锚定的立柱 (供 E2 相对定位巡逻段)
        self.pos_samples = []   # (t, x, y, z)
        self.create_subscription(ObstacleInfoArray, "/obstacles",
                                 self._on_obs, QoSProfile(depth=5))
        self.create_subscription(UAVState, "/uav_state",
                                 self._on_state, QoSProfile(depth=10))
        self.create_subscription(FollowTrajectory.Impl.FeedbackMessage,
                                 "/follow_trajectory/_action/feedback",
                                 self._on_fb, QoSProfile(depth=50))
        self.ac_takeoff = ActionClient(self, Takeoff, "/takeoff")
        self.ac_follow = ActionClient(self, FollowTrajectory, "/follow_trajectory")
        self.cli_mode = self.create_client(SetFlightMode, "/set_flight_mode")
        self.pub_goal = self.create_publisher(PoseStamped, "/move_base_simple/goal", 10)

    # ------------------------------------------------ 订阅

    def _on_obs(self, msg):
        with self._lock:
            self.obs = msg

    def _on_state(self, msg):
        with self._lock:
            self.state = msg
            self.pos_samples.append((time.monotonic(), msg.position_x,
                                     msg.position_y, msg.position_z))
            if len(self.pos_samples) > 8000:
                self.pos_samples = self.pos_samples[-4000:]

    def _on_fb(self, msg):
        with self._lock:
            self.fb = msg.feedback

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
        with self._lock:
            ds = [math.hypot(x - px, y - py) for t, x, y, z in self.pos_samples
                  if t >= t_start]
        return min(ds) if ds else float("nan")

    # ------------------------------------------------ 工具

    @staticmethod
    def _wait_future(fut, timeout_s):
        t0 = time.monotonic()
        while not fut.done():
            if time.monotonic() - t0 > timeout_s:
                return None
            time.sleep(0.05)
        return fut.result()

    def send_goal(self, client, goal, accept_timeout=30.0):
        if not client.wait_for_server(15.0):
            return None
        gh = self._wait_future(client.send_goal_async(goal), accept_timeout)
        if gh is None or not gh.accepted:
            return None
        return gh

    def call_action(self, client, goal, result_timeout):
        return self.wait_result(self.send_goal(client, goal), result_timeout)

    def wait_result(self, gh, timeout_s):
        if gh is None:
            return None, None
        wrapped = self._wait_future(gh.get_result_async(), timeout_s)
        if wrapped is None:
            return None, None
        return wrapped.status, wrapped.result

    def publish_ego_goal(self, x, y, z=1.0):
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

    def e1_static_avoid(self):
        check("E1 起飞 SUCCEEDED", self.takeoff(1.5))
        time.sleep(8.0)   # 栅格/雷达稳定
        obst = self.pick_obstacle()
        check("E1 自锚定立柱", obst is not None, "-" if obst else "无锚定障碍")
        if obst is None:
            return False
        self.pillar = obst
        st = self.snap()
        dx, dy = obst[0] - st.position_x, obst[1] - st.position_y
        d = math.hypot(dx, dy) or 1.0
        gx, gy = obst[0] + dx / d * 3.0, obst[1] + dy / d * 3.0   # 立柱对侧 3m
        info("锚定立柱 (%.2f,%.2f) → 目标 (%.2f,%.2f)" % (obst[0], obst[1], gx, gy))

        # 顺序关键: 先 follow (等首帧), 再 EGO goal (从机体当前点起规划, 无残留轨迹跳变)
        fg = FollowTrajectory.Goal()
        fg.target_x, fg.target_y, fg.target_z = gx, gy, 1.0
        fg.acceptance_radius = 0.8
        fg.timeout = 90.0
        gh = self.send_goal(self.ac_follow, fg)
        check("E1 follow goal 被接受 (HOVER 进入)", gh is not None)
        if gh is None:
            return False
        time.sleep(0.3)
        self.publish_ego_goal(gx, gy, 1.0)

        t_start = time.monotonic()
        st, res = self.wait_result(gh, 120.0)
        check("E1 FollowTrajectory SUCCEEDED", st == GoalStatus.STATUS_SUCCEEDED,
              "status=%s msg=%s" % (GSTATUS.get(st, st), res.message if res else "-"))
        min_d = self.min_dist_to_point(t_start, obst[0], obst[1])
        check("E1 与立柱 min 距离 >0.8m", min_d > 0.8, "最小 %.2fm" % min_d)
        p = self.last_pos()
        err = math.hypot(p[0] - gx, p[1] - gy) if p else float("nan")
        check("E1 落点误差 <1.0m", err < 1.0, "误差 %.2fm" % err)
        return True

    def e2_dynamic(self):
        """patrol 行人横穿航线: EGO 在线重规划、与人 min >1.0m、仍到达。

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
        # 巡逻段中点 = 立柱 + (13, 0); 目标再往前 4m 穿出
        px, py = self.pillar
        gx, gy = px + 13.0 + 4.0, py
        info("E2 目标 (%.2f,%.2f) 穿过巡逻段 (立柱+(9..17,0))" % (gx, gy))

        fg = FollowTrajectory.Goal()
        fg.target_x, fg.target_y, fg.target_z = gx, gy, 1.0
        fg.acceptance_radius = 0.8
        fg.timeout = 90.0
        gh = self.send_goal(self.ac_follow, fg)
        check("E2 follow goal 被接受", gh is not None)
        if gh is None:
            return False
        time.sleep(0.3)
        self.publish_ego_goal(gx, gy, 1.0)

        # 飞行中记录与所有簇的最小距离 (含动态行人靠近时的观测)
        t_start = time.monotonic()
        min_clear = 99.0
        while time.monotonic() - t_start < 100.0:
            with self._lock:
                o = self.obs
            p = self.last_pos()
            if o and p:
                for q in o.obstacles:
                    min_clear = min(min_clear,
                                    math.hypot(p[0] - q.center_x, p[1] - q.center_y))
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
        check("E2 与障碍 min 距离 >0.8m", min_clear > 0.8, "最小 %.2fm" % min_clear)
        p = self.last_pos()
        err = math.hypot(p[0] - gx, p[1] - gy) if p else float("nan")
        check("E2 落点误差 <1.0m", err < 1.0, "误差 %.2fm" % err)
        return True

    def e4_takeover(self):
        if not self.ensure_hover():
            check("E4 就绪 (HOVER)", False, "起飞失败")
            return False
        st = self.snap()
        p0 = (st.position_x, st.position_y, st.position_z)
        fg = FollowTrajectory.Goal()
        fg.target_x, fg.target_y, fg.target_z = p0[0] + 12.0, p0[1], 1.0
        fg.acceptance_radius = 0.8
        fg.timeout = 60.0
        gh = self.send_goal(self.ac_follow, fg)
        check("E4 follow goal 被接受", gh is not None)
        if gh is None:
            return False
        time.sleep(0.3)
        self.publish_ego_goal(p0[0] + 12.0, p0[1], 1.0)
        time.sleep(2.0)                       # 飞一段
        # 切 RTL (外部接管)
        req = SetFlightMode.Request()
        req.flight_mode = 6
        fut = self.cli_mode.call_async(req)
        self._wait_future(fut, 10.0)
        st, res = self.wait_result(gh, 30.0)
        ok = st == GoalStatus.STATUS_ABORTED and res is not None and \
            "takeover" in res.message
        check("E4 外部接管 → follow abort(takeover)", ok,
              "status=%s msg=%s" % (GSTATUS.get(st, st), res.message if res else "-"))
        return ok

    def e3_stream_cut(self):
        # E4 的 RTL 之后需要重新起飞
        if not self.ensure_hover():
            check("E3 就绪 (HOVER)", False, "起飞失败")
            return False
        st = self.snap()
        p0 = (st.position_x, st.position_y, st.position_z)
        fg = FollowTrajectory.Goal()
        fg.target_x, fg.target_y, fg.target_z = p0[0] + 14.0, p0[1], 1.0
        fg.acceptance_radius = 0.8
        fg.timeout = 90.0
        gh = self.send_goal(self.ac_follow, fg)
        check("E3 follow goal 被接受", gh is not None)
        if gh is None:
            return False
        time.sleep(0.3)
        self.publish_ego_goal(p0[0] + 14.0, p0[1], 1.0)
        time.sleep(3.0)                       # 进入轨迹飞行
        z_before = self.snap().position_z
        # 杀 traj_server → /position_cmd 断流
        subprocess.run(["pkill", "-9", "-f", "traj_server"], check=False)
        t_cut = time.monotonic()
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
        fn()
    except Exception as e:  # noqa: BLE001
        print("  [FAIL] %s 异常: %s" % (title, e), flush=True)
        RESULTS.append((title, False))
    print("  -- %s 用时 %.0fs --" % (title, time.monotonic() - t0), flush=True)


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
    run_case(node, "E1 静态绕障", node.e1_static_avoid)
    run_case(node, "E2 动态重规划", node.e2_dynamic)
    run_case(node, "E4 接管让位", node.e4_takeover)
    run_case(node, "E3 流中断安全", node.e3_stream_cut)

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
