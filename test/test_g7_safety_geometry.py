#!/usr/bin/env python3
"""G7/N2 不依赖 ROS 的几何回归测试。"""

import math
import unittest

from g7_geometry import (JumpGuardModel, WaypointLifecycleModel,
                         min_clearance_to_aabb, segment_clearance_to_aabb,
                         signed_clearance_to_aabb,
                         obstacle_observation_rejection_reason,
                         update_obstacle_clusters)


class G7SafetyGeometryTest(unittest.TestCase):

    def test_inflated_box_reports_penetration(self):
        # 1x1m obstacle + 0.5m inflation: (0,0) 位于膨胀 AABB 内。
        self.assertLess(signed_clearance_to_aabb(0.0, 0.0, 0.0, 0.0,
                                                 1.0, 1.0, 0.5), 0.0)

    def test_diagonal_clearance_uses_aabb_corner_distance(self):
        # 膨胀后半尺寸 1.0m，(2,2) 到角点为 sqrt(2)。
        self.assertAlmostEqual(
            signed_clearance_to_aabb(2.0, 2.0, 0.0, 0.0, 1.0, 1.0, 0.5),
            math.sqrt(2.0), places=6)

    def test_trajectory_minimum_is_not_center_distance(self):
        samples = [(0.0, -2.0), (1.4, 0.0), (0.0, 2.0)]
        clearance = min_clearance_to_aabb(
            samples, 0.0, 0.0, 2.0, 2.0, 0.5)
        self.assertLess(clearance, 0.0)

    def test_segment_clearance_catches_sparse_sampled_crossing(self):
        # 两个采样点都在障碍足迹外，但中间线段穿过膨胀 AABB；
        # 只检查采样点会错误地判定安全。
        clearance = segment_clearance_to_aabb(
            (-2.0, 0.0), (2.0, 0.0), 0.0, 0.0, 1.0, 1.0, 0.5)
        self.assertLess(clearance, 0.0)

    def test_jump_guard_rejected_frames_do_not_accumulate_dt(self):
        guard = JumpGuardModel()
        self.assertTrue(guard.observe(7, (0.0, 0.0, 0.0), 0.0))
        # 持续的 519m 假目标即使发布很久，也必须逐帧被拒绝；如果 dt
        # 从最后接受帧累积，旧实现会在等待后错误放行。
        for index in range(1, 20):
            self.assertFalse(guard.observe(7, (519.0, 0.0, 0.0), index * 0.1))

    def test_obstacle_clusters_keep_adjacent_objects_and_max_size(self):
        clusters = []
        update_obstacle_clusters(
            clusters,
            [(4.0, 0.0, 1.0, 1.0, 1.0), (4.8, 0.0, 0.8, 0.8, 0.8)],
            sequence=1,
            association_radius=0.6)
        self.assertEqual(len(clusters), 2)
        update_obstacle_clusters(
            clusters, [(4.05, 0.02, 1.6, 1.2, 1.1)], sequence=2,
            association_radius=0.6)
        nearest = min(clusters, key=lambda c: abs(c.center_x - 4.05))
        self.assertEqual(nearest.count, 2)
        self.assertEqual(nearest.max_size_x, 1.6)

    def test_local_pillar_slice_passes_filter_and_stable_votes(self):
        clusters = []
        observation = (4.5, 0.0, 1.05, 1.10, 0.20)
        for sequence in range(1, 4):
            self.assertIsNone(obstacle_observation_rejection_reason(
                observation, (0.0, 0.0), 3.0, 8.0, 2.5))
            update_obstacle_clusters(
                clusters, [observation], sequence, association_radius=0.6)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].count, 3)
        self.assertAlmostEqual(clusters[0].max_size_z, 0.20)

    def test_obstacle_filter_keeps_safety_rejections(self):
        base = (4.5, 0.0, 1.0, 1.0, 0.20)
        self.assertEqual(
            obstacle_observation_rejection_reason(
                (4.5, 0.0, 1.0, 1.0, 0.14), (0.0, 0.0), 3.0, 8.0, 2.5),
            "visible_height")
        self.assertEqual(
            obstacle_observation_rejection_reason(
                (9.0, 0.0, 1.0, 1.0, 0.20), (0.0, 0.0), 3.0, 8.0, 2.5),
            "distance")
        self.assertEqual(
            obstacle_observation_rejection_reason(
                (4.5, 0.0, 3.0, 1.0, 0.20), (0.0, 0.0), 3.0, 8.0, 2.5),
            "xy_size")
        self.assertEqual(
            obstacle_observation_rejection_reason(
                (float("nan"), base[1], base[2], base[3], base[4]),
                (0.0, 0.0), 3.0, 8.0, 2.5),
            "nonfinite")

    def test_waypoint_timeout_keeps_child_non_idle_until_terminal(self):
        child = WaypointLifecycleModel()
        self.assertTrue(child.start_send())
        self.assertFalse(child.may_issue)
        self.assertTrue(child.request_cancel())
        # send future 尚未解析时以及 cancel 未收到终态时都不能发新 child。
        self.assertFalse(child.may_issue)
        self.assertTrue(child.resolve_send(True))
        self.assertEqual(child.state, child.ACTIVE)
        self.assertTrue(child.request_cancel())
        self.assertFalse(child.may_issue)
        self.assertTrue(child.terminal())
        self.assertTrue(child.may_issue)


if __name__ == "__main__":
    unittest.main()
