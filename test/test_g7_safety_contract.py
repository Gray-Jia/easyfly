#!/usr/bin/env python3
"""G7 关键安全契约的静态回归测试（不需要 ROS/SITL）。"""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
TRACKING_CPP = (ROOT / "src/execution/e3_control/easyfly_target_tracking/src/"
                "target_tracking_node.cpp").read_text()
TRACKING_YAML = (
    ROOT / "src/execution/e3_control/easyfly_target_tracking/config/"
    "follow.yaml"
).read_text()
FOLLOW_TEST = (ROOT / "test/follow_acceptance.py").read_text()
NAV_TEST = (ROOT / "test/navigate_acceptance.py").read_text()
GLOBAL_CPP = (ROOT / "src/execution/e2_planning/easyfly_global_planner/src/"
              "global_planner_node.cpp").read_text()
GLOBAL_GOAL_VALIDATION = (
    ROOT / "src/execution/e2_planning/easyfly_global_planner/include/"
    "easyfly_global_planner/goal_validation.hpp").read_text()
GLOBAL_CMAKE = (ROOT / "src/execution/e2_planning/easyfly_global_planner/CMakeLists.txt").read_text()
SEMANTIC_CPP = (ROOT / "src/perception/p4_fusion/easyfly_semantic_map/src/"
                "semantic_map_node.cpp").read_text()
SEMANTIC_PACKAGE = (ROOT / "src/perception/p4_fusion/easyfly_semantic_map/package.xml").read_text()
TRACKING_LIFECYCLE = (ROOT / "src/execution/e3_control/easyfly_target_tracking/"
                      "include/easyfly_target_tracking/waypoint_lifecycle.hpp").read_text()
TRACKING_FRAME = (ROOT / "src/execution/e3_control/easyfly_target_tracking/"
                  "include/easyfly_target_tracking/target_frame.hpp").read_text()
GLOBAL_MAP_VALIDITY = (ROOT / "src/execution/e2_planning/easyfly_global_planner/"
                       "include/easyfly_global_planner/map_validity.hpp").read_text()


class G7SafetyContractTest(unittest.TestCase):

    def test_follow_radius_covers_sitl_but_is_finite(self):
        match = re.search(r"^\s*max_follow_radius:\s*([0-9.]+)", TRACKING_YAML,
                          re.MULTILINE)
        self.assertIsNotNone(match)
        radius = float(match.group(1))
        self.assertGreaterEqual(radius, 22.0)
        self.assertLess(radius, 100.0)

    def test_jump_guard_never_accepts_streak(self):
        self.assertNotIn("jump_accept_streak", TRACKING_YAML)
        self.assertNotIn("streak_", TRACKING_CPP)
        self.assertIn("guard_generation_", TRACKING_CPP)
        self.assertIn("max_target_jump", TRACKING_CPP)

    def test_reacquire_preserves_class_and_aborts_safety_violation(self):
        self.assertIn("expected_class", TRACKING_CPP)
        self.assertIn('abnormal_reason = "target class changed"', TRACKING_CPP)
        self.assertIn(
            'abnormal_reason = "target outside max follow radius"',
            TRACKING_CPP)
        self.assertIn(
            "cancelWaypointUntilTerminal(",
            TRACKING_CPP)
        self.assertIn("reacquire candidate outside max follow radius", TRACKING_CPP)
        self.assertIn("gh->abort(res)", TRACKING_CPP)

    def test_acceptance_feedback_is_goal_scoped(self):
        self.assertIn("_feedback_goal_id", FOLLOW_TEST)
        self.assertIn("msg.goal_id", FOLLOW_TEST)
        self.assertIn("wait_follow_established", FOLLOW_TEST)

    def test_navigation_requires_fresh_obstacles_and_uses_aabb(self):
        self.assertIn("obs_seq", NAV_TEST)
        self.assertIn("min_votes=3", NAV_TEST)
        self.assertIn("min_clearance_to_aabb", NAV_TEST)
        self.assertIn("grid_occupied_goal(min_seq=", NAV_TEST)
        self.assertIn("N2 构造目标不在新鲜占据格", NAV_TEST)
        self.assertIn("update_obstacle_clusters", NAV_TEST)
        self.assertIn("max_size_x", (ROOT / "test/g7_geometry.py").read_text())

    def test_navigation_teardown_stops_spin_before_rclpy_shutdown(self):
        main = NAV_TEST[NAV_TEST.index("def main():"):]
        self.assertIn("spin_thread = threading.Thread(target=ex.spin", main)
        self.assertNotIn("threading.Thread(target=ex.spin, daemon=True).start()", main)
        self.assertIn("finally:", main)
        executor_shutdown = main.index("ex.shutdown()")
        spin_join = main.index("spin_thread.join")
        node_destroy = main.index("node.destroy_node()")
        ros_shutdown = main.index("rclpy.shutdown()")
        self.assertLess(executor_shutdown, spin_join)
        self.assertLess(spin_join, node_destroy)
        self.assertLess(node_destroy, ros_shutdown)
        self.assertIn("if ex is not None:", main)
        self.assertIn("if spin_thread is not None:", main)
        self.assertIn("if node is not None:", main)

    def test_waypoint_and_state_safety_contracts(self):
        self.assertIn("wp_pending", TRACKING_CPP)
        self.assertIn("child cancellation required", TRACKING_CPP)
        self.assertIn("child_cancel_max_wait", TRACKING_CPP)
        self.assertIn("child_fault_", TRACKING_CPP)
        self.assertIn("state_timeout", TRACKING_CPP)
        self.assertIn("last_observation_time_", TRACKING_CPP)

    def test_global_admission_and_child_lifecycle_contracts(self):
        planner = GLOBAL_CPP
        lifecycle = (ROOT / "src/execution/e2_planning/easyfly_global_planner/include/"
                     "easyfly_global_planner/waypoint_lifecycle.hpp").read_text()
        self.assertIn("pending_goal_uuid_", planner)
        self.assertIn("active_goal_", planner)
        self.assertIn("cancelWaypointUntilTerminal", planner)
        self.assertIn("child_cancel_max_wait", planner)
        self.assertIn("kSending", lifecycle)
        self.assertIn("confirmTerminal", lifecycle)
        self.assertIn("kRecovering", lifecycle)
        self.assertIn("enterRecovery", lifecycle)
        self.assertIn("async_cancel_all_goals", planner)
        self.assertIn("async_cancel_all_goals", TRACKING_CPP)

    def test_recovery_and_state_snapshot_contracts(self):
        self.assertIn("kRecovering", TRACKING_LIFECYCLE)
        self.assertIn("enterRecovery", TRACKING_LIFECYCLE)
        self.assertIn("state_arrival_", GLOBAL_CPP)
        self.assertIn("state_timeout", GLOBAL_CPP)
        self.assertIn("StateSnapshot", GLOBAL_CPP)

    def test_navigation_goal_numeric_contract(self):
        self.assertIn("validNavigateGoal", GLOBAL_CPP)
        self.assertIn("std::isfinite(goal.target_x)", GLOBAL_GOAL_VALIDATION)
        self.assertIn("std::isfinite(goal.target_y)", GLOBAL_GOAL_VALIDATION)
        self.assertIn("!std::isinf(goal.target_z)", GLOBAL_GOAL_VALIDATION)
        self.assertIn("std::isfinite(goal.max_speed)", GLOBAL_GOAL_VALIDATION)
        self.assertIn("test_goal_validation", GLOBAL_CMAKE)

    def test_coordinate_frames_fail_closed_after_first_message(self):
        self.assertIn('kWorldFrame[] = "odom"', GLOBAL_MAP_VALIDITY)
        self.assertIn("grid.header.frame_id != kWorldFrame", GLOBAL_MAP_VALIDITY)
        self.assertIn("std::isfinite(grid.info.resolution)", GLOBAL_MAP_VALIDITY)
        self.assertIn("std::isfinite(grid.info.origin.position.x)", GLOBAL_MAP_VALIDITY)
        self.assertIn("std::isfinite(grid.info.origin.position.y)", GLOBAL_MAP_VALIDITY)
        self.assertIn('kTargetWorldFrame[] = "odom"', TRACKING_FRAME)
        self.assertIn("arr.generation > 0", TRACKING_CPP)
        self.assertIn("targetArrayFrameValid", TRACKING_CPP)
        self.assertIn("grid_received_", GLOBAL_CPP)
        self.assertIn("waitForFirstGrid", GLOBAL_CPP)

    def test_semantic_map_declares_yaml_cpp_runtime_dependency(self):
        self.assertIn("<depend>yaml-cpp</depend>", SEMANTIC_PACKAGE)
        ground_header = (ROOT / "src/perception/p4_fusion/easyfly_semantic_map/include/"
                         "easyfly_semantic_map/ground_plane_tracker.hpp").read_text()
        self.assertIn("P2 concern", ground_header)
        self.assertIn("landed/contact", ground_header)

    def test_semantic_ground_init_uses_bridged_flight_state_only(self):
        self.assertIn("vehicle.connected", (
            ROOT / "src/perception/p4_fusion/easyfly_semantic_map/include/"
            "easyfly_semantic_map/ground_plane_tracker.hpp").read_text())
        self.assertIn("pose.armed", SEMANTIC_CPP)
        self.assertNotIn("gps_valid", SEMANTIC_CPP)
        self.assertNotIn("relative_altitude", SEMANTIC_CPP)

    def test_feedback_sampling_requires_new_sequences(self):
        self.assertIn("_feedback_seq", FOLLOW_TEST)
        self.assertIn("seq != last_seq", FOLLOW_TEST)
        self.assertIn("F3 新鲜 feedback 覆盖率", FOLLOW_TEST)


if __name__ == "__main__":
    unittest.main()
