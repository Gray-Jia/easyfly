#!/usr/bin/env python3
"""
control_regression.py — EasyFly 控制链回归测试 (question.md Q32 轻量实现)

把 test-guide.md 的手动回归流程脚本化, 覆盖项:

  T1  就绪检查     /uav_state 数据流 + 模式有效 + 4 个 action server + EKF 稳定余量
  T2  起飞         2.5m; 完成后悬停精度 / armed / OFFBOARD
  T3  航点往返     (6,0,2.5)→(0.5,0,2.5); 位置精度 <1.0m
  T4  航点取消     取消后就地悬停 (P0/Q4): 不得飞到目标, 保持 OFFBOARD
  T5  降落取消     恢复悬停 (P0/Q3): 模式切回 OFFBOARD, 高度回升
  T6  连续起降 ×2  降落 disarm 后可再次起飞 (复查缺陷 D 回归)
  T7  坏任务文件   mission abort 且节点存活 (P0/Q8: 非法数值不崩溃)
  T8  低电量 RTL   注入 10% 电量 → 任务 EMERGENCY abort + PX4 AUTO.RTL (Q2/外部接管检测)

已知仿真怪癖 (test-guide.md 第六节, 非代码缺陷):
  - SITL 连续 3+ 轮起降后磁力计可能退化报 failsafe — 本套件共 4 次起飞,
    末尾用例若因此失败, 重跑即可 (run_control_regression.sh 每次重启仿真);
  - RTL 返航降落 ~2 分钟, T8 的"落地 disarm / 降后再起飞"只做信息性检查 (非硬断言)。

前置: run_control_regression.sh 已启动 test/control_regression.launch.py 仿真环境。
用法: python3 control_regression.py [--skip-flight]   (仅跑地面用例 T7)
退出码: 0=全部硬断言通过, 1=有失败
"""

import argparse
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
from easyfly_msgs.action import ExecuteMission, GoToWaypoint, Land, Takeoff
from easyfly_msgs.msg import UAVState
from sensor_msgs.msg import BatteryState

RTL_MISSION = "/tmp/easyfly_rtl_mission.yaml"
BAD_MISSION = "/tmp/easyfly_bad_mission.yaml"

GSTATUS = {
    GoalStatus.STATUS_ACCEPTED: "ACCEPTED",
    GoalStatus.STATUS_EXECUTING: "EXECUTING",
    GoalStatus.STATUS_CANCELING: "CANCELING",
    GoalStatus.STATUS_SUCCEEDED: "SUCCEEDED",
    GoalStatus.STATUS_CANCELED: "CANCELED",
    GoalStatus.STATUS_ABORTED: "ABORTED",
    GoalStatus.STATUS_UNKNOWN: "UNKNOWN",
}


class RegressionRunner(Node):

    def __init__(self):
        super().__init__("easyfly_control_regression")
        self._state = None
        self._state_mtx = threading.Lock()
        self.create_subscription(
            UAVState, "/uav_state", self._on_state, QoSProfile(depth=10))

        self.ac_takeoff = ActionClient(self, Takeoff, "/takeoff")
        self.ac_land = ActionClient(self, Land, "/land")
        self.ac_wp = ActionClient(self, GoToWaypoint, "/goto_waypoint")
        self.ac_mission = ActionClient(self, ExecuteMission, "/execute_mission")

        self._bat_pub = self.create_publisher(BatteryState, "/mavros/battery", 10)
        self._bat_stop = threading.Event()

    # ------------------------------------------------ 状态

    def _on_state(self, msg):
        with self._state_mtx:
            self._state = msg

    def snap(self):
        with self._state_mtx:
            return self._state

    # ------------------------------------------------ 通用工具

    @staticmethod
    def _wait_future(fut, timeout_s):
        t0 = time.monotonic()
        while not fut.done():
            if time.monotonic() - t0 > timeout_s:
                return None
            time.sleep(0.05)
        return fut.result()

    def send_goal(self, client, goal, accept_timeout=60.0):
        """发送 goal 并等接受. 返回 goal handle (被拒/超时为 None)。"""
        if not client.wait_for_server(10.0):
            log("  action server 不可用 (10s)")
            return None
        gh = self._wait_future(client.send_goal_async(goal), accept_timeout)
        if gh is None or not gh.accepted:
            return None
        return gh

    def wait_result(self, gh, timeout_s):
        """等待 goal 终态. 返回 (status:int|None, result|None)。"""
        if gh is None:
            return None, None
        wrapped = self._wait_future(gh.get_result_async(), timeout_s)
        if wrapped is None:
            return None, None
        return wrapped.status, wrapped.result

    def call_action(self, client, goal, result_timeout):
        return self.wait_result(self.send_goal(client, goal), result_timeout)

    def inject_low_battery(self, duration_s, percentage=0.10, voltage=13.0):
        """以 10Hz 向 /mavros/battery 注入低电量 (test-guide.md 附录验证流程同款)。

        与 mavros 真实电量消息交织, bridge 取最后到达值; 10Hz 密度下
        mission_fsm 1Hz safety_check 读到的几乎总是注入值。返回停止函数。
        """
        self._bat_stop.clear()
        stop_evt = self._bat_stop

        def _run():
            msg = BatteryState()
            msg.voltage = voltage
            msg.percentage = percentage
            t0 = time.monotonic()
            while not stop_evt.is_set() and time.monotonic() - t0 < duration_s:
                self._bat_pub.publish(msg)
                time.sleep(0.1)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return stop_evt.set

    # ------------------------------------------------ 用例

    def t1_ready(self):
        deadline = time.monotonic() + 60.0
        while self.snap() is None:
            if time.monotonic() > deadline:
                raise RuntimeError("60s 内未收到 /uav_state (mavlink_bridge 未启动?)")
            time.sleep(0.2)

        deadline = time.monotonic() + 60.0
        while True:
            s = self.snap()
            if s.flight_mode != 99 and math.isfinite(s.position_x):
                break
            if time.monotonic() > deadline:
                raise RuntimeError("模式无效 (flight_mode=99), PX4/mavros 未就绪")
            time.sleep(0.3)

        for c, name in ((self.ac_takeoff, "/takeoff"), (self.ac_land, "/land"),
                        (self.ac_wp, "/goto_waypoint"), (self.ac_mission, "/execute_mission")):
            if not c.wait_for_server(30.0):
                raise RuntimeError("action server 不可用: %s" % name)

        # EKF 稳定余量 (test-guide: Ready for takeoff 需 30-60s)
        info("等待 EKF/GPS 收敛 (30s)...")
        time.sleep(30.0)
        return True

    def t2_takeoff(self):
        # arm 失败 (EKF 收敛边缘) 时按 test-guide 手动流程: 等待后重发一次
        for attempt in (1, 2):
            st, res = self.call_action(self.ac_takeoff, self._takeoff_goal(2.5), 120.0)
            if st == GoalStatus.STATUS_SUCCEEDED:
                break
            msg = res.message if res else "-"
            if attempt == 1 and "arm failed" in msg:
                info("首次 arm 失败 (EKF 收敛边缘), 等待 20s 后按手动流程重发...")
                time.sleep(20.0)
                continue
            break
        check("T2 起飞 action SUCCEEDED", st == GoalStatus.STATUS_SUCCEEDED,
              "status=%s result=%s" % (GSTATUS.get(st, st), res.message if res else "-"))
        time.sleep(2.0)
        s = self.snap()
        check("T2 悬停高度 ~2.5m", s is not None and abs(s.position_z - 2.5) < 0.6,
              "z=%.2f" % (s.position_z if s else float("nan")))
        check("T2 armed + OFFBOARD", s is not None and s.armed and s.flight_mode == 3,
              "armed=%s mode=%d" % (s.armed if s else "-", s.flight_mode if s else -1))
        return True

    def t3_waypoints(self):
        ok = True
        for tag, (tx, ty) in (("去程", (6.0, 0.0)), ("返程", (0.5, 0.0))):
            g = GoToWaypoint.Goal()
            g.target_x, g.target_y, g.target_z = tx, ty, 2.5
            g.max_speed = 2.0
            st, res = self.call_action(self.ac_wp, g, 90.0)
            good = st == GoalStatus.STATUS_SUCCEEDED
            ok &= good
            check("T3 航点%s SUCCEEDED" % tag, good,
                  "status=%s" % GSTATUS.get(st, st))
            time.sleep(2.0)
            s = self.snap()
            d = math.hypot(s.position_x - tx, s.position_y - ty) if s else float("nan")
            check("T3 航点%s 位置精度 <1.0m" % tag, d < 1.0, "水平偏差=%.2fm" % d)
        return ok

    def t4_cancel_waypoint(self):
        g = GoToWaypoint.Goal()
        g.target_x, g.target_y, g.target_z = 12.0, 0.0, 2.5
        g.max_speed = 2.0
        gh = self.send_goal(self.ac_wp, g)
        check("T4 目标航点被接受", gh is not None, "-")
        time.sleep(4.0)  # 2m/s 已飞出数米

        cfut = gh.cancel_goal_async()
        self._wait_future(cfut, 10.0)
        st, _ = self.wait_result(gh, 30.0)
        check("T4 取消后终态 CANCELED", st == GoalStatus.STATUS_CANCELED,
              "status=%s" % GSTATUS.get(st, st))

        time.sleep(3.0)  # 惯性过冲稳定 (test-guide: 过冲 ~1m)
        s = self.snap()
        d = math.hypot(s.position_x - 12.0, s.position_y) if s else float("nan")
        check("T4 未飞到目标 (就地悬停)", d > 1.5, "距目标=%.2fm" % d)
        check("T4 保持 OFFBOARD + armed", s is not None and s.armed and s.flight_mode == 3,
              "armed=%s mode=%d" % (s.armed if s else "-", s.flight_mode if s else -1))
        check("T4 高度未失控", s is not None and 1.2 < s.position_z < 3.8,
              "z=%.2f" % (s.position_z if s else float("nan")))
        return True

    def t5_cancel_land(self):
        gh = self.send_goal(self.ac_land, Land.Goal())
        check("T5 降落 goal 被接受", gh is not None, "-")
        time.sleep(2.0)  # AUTO.LAND 下降 ~1m

        cfut = gh.cancel_goal_async()
        self._wait_future(cfut, 10.0)
        st, _ = self.wait_result(gh, 30.0)
        check("T5 取消后终态 CANCELED", st == GoalStatus.STATUS_CANCELED,
              "status=%s" % GSTATUS.get(st, st))

        # 恢复悬停: 切回 OFFBOARD + 高度回升 (P0/Q3: 原实现会继续降到底)
        ok = False
        min_z = 99.0
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            s = self.snap()
            if s is None:
                time.sleep(0.3)
                continue
            min_z = min(min_z, s.position_z)
            if s.flight_mode == 3 and s.armed and s.position_z > 1.8:
                ok = True
                break
            time.sleep(0.3)
        check("T5 恢复 OFFBOARD + 高度回升", ok,
              "mode=%d z=%.2f (取消后最低 %.2f)" %
              (s.flight_mode if s else -1, s.position_z if s else float("nan"), min_z))
        return ok

    def t6_land_then_cycles(self):
        # 先从 T5 的悬停态完整降落一次 → active_=NONE, 后续 takeoff 才被接受
        st, res = self.call_action(self.ac_land, Land.Goal(), 90.0)
        check("T6a 补一次完整降落 SUCCEEDED", st == GoalStatus.STATUS_SUCCEEDED,
              "status=%s" % GSTATUS.get(st, st))
        time.sleep(3.0)
        s = self.snap()
        check("T6a 降落已 disarm", s is not None and not s.armed,
              "armed=%s" % (s.armed if s else "-"))

        for i in (1, 2):  # 缺陷 D 回归: 降落后的第 1/2 次再起飞
            g = Takeoff.Goal()
            g.target_altitude = 2.0
            g.climb_speed = 1.0
            st, _ = self.call_action(self.ac_takeoff, g, 120.0)
            check("T6b 第%d轮起飞 SUCCEEDED" % i, st == GoalStatus.STATUS_SUCCEEDED,
                  "status=%s" % GSTATUS.get(st, st))
            st, _ = self.call_action(self.ac_land, Land.Goal(), 90.0)
            check("T6b 第%d轮降落 SUCCEEDED" % i, st == GoalStatus.STATUS_SUCCEEDED,
                  "status=%s" % GSTATUS.get(st, st))
            time.sleep(3.0)
        return True

    def t7_bad_mission(self):
        with open(BAD_MISSION, "w") as f:
            f.write("type=takeoff\naltitude=2.5米\n---\ntype=land\n")  # Q8 毒数据
        g = ExecuteMission.Goal()
        g.mission_file = BAD_MISSION
        st, res = self.call_action(self.ac_mission, g, 60.0)
        check("T7 坏任务文件被 abort", st == GoalStatus.STATUS_ABORTED and
              res is not None and not res.success,
              "status=%s success=%s msg=%r" %
              (GSTATUS.get(st, st), res.success if res else "-", res.message if res else "-"))
        return True

    def t8_low_battery_rtl(self):
        with open(RTL_MISSION, "w") as f:
            f.write("type=takeoff\naltitude=2.0\nclimb_speed=1.0\n"
                    "---\ntype=hover\nwait=120.0\n")
        g = ExecuteMission.Goal()
        g.mission_file = RTL_MISSION
        gh = self.send_goal(self.ac_mission, g)
        check("T8 任务被接受", gh is not None, "-")

        # 等任务起飞完成 (mode==OFFBOARD, z>1.5)
        ok = False
        deadline = time.monotonic() + 90.0
        while time.monotonic() < deadline:
            s = self.snap()
            if s and s.armed and s.flight_mode == 3 and s.position_z > 1.5:
                ok = True
                break
            time.sleep(0.5)
        check("T8 任务起飞到位", ok,
              "armed=%s mode=%d z=%.2f" %
              (s.armed if s else "-", s.flight_mode if s else -1,
               s.position_z if s else float("nan")))

        # 注入低电量 → 期望: mission EMERGENCY abort + PX4 AUTO.RTL (mode 6)
        stop_bat = self.inject_low_battery(duration_s=45.0)
        saw_rtl = False
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            s = self.snap()
            if s and s.flight_mode == 6:
                saw_rtl = True
                break
            time.sleep(0.3)
        time.sleep(2.0)
        stop_bat()
        check("T8 PX4 进入 AUTO.RTL (mode=6)", saw_rtl,
              "mode=%d" % (s.flight_mode if s else -1))

        st, res = self.wait_result(gh, 60.0)
        check("T8 任务 EMERGENCY abort", st == GoalStatus.STATUS_ABORTED,
              "status=%s msg=%r" % (GSTATUS.get(st, st), res.message if res else "-"))

        # ---- 信息性检查 (非硬断言): RTL 落地 ~2min; 降落后可再起飞 ----
        info("T8 [信息] 等待 RTL 落地 disarm (最长 240s, SITL RTL 含虚拟 home 距离)...")
        disarmed = False
        deadline = time.monotonic() + 240.0
        while time.monotonic() < deadline:
            s = self.snap()
            if s and not s.armed:
                disarmed = True
                break
            time.sleep(1.0)
        info("T8 [信息] RTL 落地 disarm: %s" % ("是" if disarmed else "超时未确认 (RTL 尚在进行?)"))
        if disarmed:
            time.sleep(5.0)
            st, _ = self.call_action(self.ac_takeoff,
                                     self._takeoff_goal(1.5), 120.0)
            info("T8 [信息] RTL 降落后再次起飞: %s" % GSTATUS.get(st, st))
            if st == GoalStatus.STATUS_SUCCEEDED:
                self.call_action(self.ac_land, Land.Goal(), 90.0)
        return saw_rtl and st == GoalStatus.STATUS_ABORTED

    @staticmethod
    def _takeoff_goal(alt):
        g = Takeoff.Goal()
        g.target_altitude = alt
        g.climb_speed = 1.0
        return g


# ------------------------------------------------ 框架

_log_mtx = threading.Lock()
RESULTS = []


def log(msg):
    with _log_mtx:
        print(msg, flush=True)


def info(msg):
    log("  %s" % msg)


def check(name, ok, detail="-"):
    log("  [%s] %s   (%s)" % ("PASS" if ok else "FAIL", name, detail))
    RESULTS.append((name, ok))
    return ok


def run_test(node, title, fn):
    log("\n== %s ==" % title)
    t0 = time.monotonic()
    try:
        fn()
        ok = all(r for n, r in RESULTS if n.startswith(title.split()[0]))
    except Exception as e:  # noqa: BLE001 — 用例内任何异常都视为该用例失败
        log("  [FAIL] %s 异常: %s" % (title, e))
        ok = False
        RESULTS.append((title, False))
    log("  -- %s 用时 %.0fs --" % (title, time.monotonic() - t0))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-flight", action="store_true",
                    help="只跑地面用例 T7 (调试用)")
    args = ap.parse_args()

    rclpy.init()
    node = RegressionRunner()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    threading.Thread(target=executor.spin, daemon=True).start()

    log("=" * 60)
    log("EasyFly 控制链回归测试")
    log("=" * 60)

    results = {}
    if not args.skip_flight:
        results["T1"] = run_test(node, "T1 就绪检查", node.t1_ready)
        results["T2"] = run_test(node, "T2 起飞", node.t2_takeoff)
        flight_ready = results["T1"] and results["T2"]
        results["T3"] = run_test(node, "T3 航点往返", node.t3_waypoints) if flight_ready else False
        results["T4"] = run_test(node, "T4 航点取消", node.t4_cancel_waypoint) if flight_ready else False
        results["T5"] = run_test(node, "T5 降落取消", node.t5_cancel_land) if flight_ready else False
        results["T6"] = run_test(node, "T6 连续起降", node.t6_land_then_cycles) if flight_ready else False
        results["T7"] = run_test(node, "T7 坏任务文件", node.t7_bad_mission)
        results["T8"] = run_test(node, "T8 低电量RTL", node.t8_low_battery_rtl) if flight_ready else False
    else:
        results["T7"] = run_test(node, "T7 坏任务文件", node.t7_bad_mission)

    log("\n" + "=" * 60)
    log("结果汇总:")
    failed = 0
    for k in sorted(results):
        log("  %s  %s" % ("PASS" if results[k] else "FAIL", k))
        failed += 0 if results[k] else 1
    log("=" * 60)

    executor.shutdown()
    rclpy.shutdown()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
