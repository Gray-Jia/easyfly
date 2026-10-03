"""Static contracts for the V2-19 safety and EGO data-path changes.

These tests intentionally do not import ROS.  They make the critical wiring
and sequencing contracts executable in a plain Python environment; dynamic
SITL acceptance remains a separate gate.
"""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
FLIGHT = ROOT / "src/execution/e3_control/easyfly_flight_control"
EGO = ROOT / "src/third_party/planners/ego_planner"
SEMANTIC = ROOT / "src/perception/p4_fusion/easyfly_semantic_map"
LOCAL = ROOT / "src/execution/e2_planning/easyfly_local_planner"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_finish_helpers_own_goal_handle_copy_and_takeover_test_exists():
    header = read(FLIGHT / "include/easyfly_flight_control/flight_controller.hpp")
    for action in ("Takeoff", "Land", "GoToWaypoint", "FollowTrajectory"):
        pattern = rf"finish_[a-z_]+\(\s*\n\s*std::shared_ptr<rclcpp_action::ServerGoalHandle<{action}>> gh"
        assert re.search(pattern, header), action
    source = read(FLIGHT / "src/flight_controller.cpp")
    for action in ("Takeoff", "Land", "GoToWaypoint", "FollowTrajectory"):
        pattern = rf"FlightController::finish_[a-z_]+\(\s*\n\s*std::shared_ptr<rclcpp_action::ServerGoalHandle<{action}>> gh"
        assert re.search(pattern, source), action
    mock = read(ROOT / "test/p0_flight_controller_mock.py")
    assert "active trajectory external takeover aborts without action-server crash" in mock


def test_ego_uses_node_clock_for_ros_time_and_steady_clock_for_budgets():
    manager = read(EGO / "plan_manage/src/planner_manager.cpp")
    fsm = read(EGO / "plan_manage/src/ego_replan_fsm.cpp")
    optimizer = read(EGO / "bspline_opt/src/bspline_optimizer.cpp")
    assert "clock_ = nh->get_clock()" in manager
    assert "std::chrono::steady_clock" in manager
    assert "std::chrono::steady_clock" in optimizer
    assert "node_->get_clock()->now()" in fsm
    assert "(t_init + t_opt + t_refine).seconds()" not in manager
    assert "_clock.now()" not in manager + fsm + optimizer


def test_trusted_nonground_cloud_is_the_only_ego_input():
    semantic = read(SEMANTIC / "src/semantic_map_node.cpp")
    launch = read(LOCAL / "launch/local_planner.launch.py")
    config = read(SEMANTIC / "config/semantic_map.yaml")
    assert "nonground_topic{\"/pointcloud_nonground\"}" in semantic
    assert "nonground_pub_->publish(nonground_msg)" in semantic
    assert "if (!ground_tracker_.initialized())" in semantic
    assert "nonground_topic: /pointcloud_nonground" in config
    assert "('grid_map/cloud', '/pointcloud_nonground')" in launch
    assert "('grid_map/cloud', '/pointcloud_filtered')" not in launch
    assert "模型未就绪时发布空云，不能回退到原始地面点云" in launch


def test_ego_cloud_freshness_is_fail_closed_and_traj_goal_is_bounded():
    grid_header = read(EGO / "plan_env/include/plan_env/grid_map.h")
    grid_source = read(EGO / "plan_env/src/grid_map.cpp")
    fsm = read(EGO / "plan_manage/src/ego_replan_fsm.cpp")
    launch = read(LOCAL / "launch/local_planner.launch.py")
    flight = read(FLIGHT / "src/flight_controller.cpp")
    assert "PLAN_ENV_PUBLIC bool hasFreshTrustedCloud();" in grid_header
    assert "last_trusted_cloud_time_" in grid_header
    assert "last_odom_sample_" in grid_header
    assert "odom_clock_valid_" in grid_header
    assert "trusted_cloud_timeout" in grid_source
    assert "odom_freshness_timeout" in grid_source
    assert "max_trusted_cloud_points" in grid_source
    assert "md_.has_cloud_ = false" in grid_source
    assert "node_->get_clock()->now()" in grid_source
    assert "if (!checkOdomFreshness())" in grid_source
    assert "std::numeric_limits<std::uint64_t>::max() / height" in grid_source
    assert "raw_point_count > static_cast<std::uint64_t>(mp_.max_trusted_cloud_points_)" in grid_source
    assert "if (!hasFreshTrustedCloud())" in fsm
    assert "NO_TRUSTED_CLOUD" in fsm
    assert "grid_map/trusted_cloud_timeout': 1.0" in launch
    assert "grid_map/odom_freshness_timeout': 1.0" in launch
    assert "grid_map/max_trusted_cloud_points': 200000" in launch
    traj_goal = flight[flight.index("GoalResponse FlightController::handle_traj_goal"):]
    assert "g->target_x - uav.position_x" in traj_goal
    assert "max_goal_distance_" in traj_goal


def test_trajectory_startup_grace_cannot_extend_action_deadline():
    timeout_header = read(
        FLIGHT / "include/easyfly_flight_control/trajectory_startup_timeout.hpp")
    flight = read(FLIGHT / "src/flight_controller.cpp")
    assert "trajectoryStartupTimedOut" in timeout_header
    assert "trajectoryDeadlineExpired" in timeout_header
    assert "traj_deadline_ - traj_accept_time_" in flight
    assert "traj_deadline_ - wait_now" in flight
    assert "trajectory_timeout_before_start" in flight
    assert "trajectory_start_timeout" in flight

    callback = flight[flight.index("void FlightController::cb_position_cmd"):]
    callback = callback[:callback.index("easyfly_msgs::msg::UAVState")]
    callback_deadline_check = callback.index("trajectoryStartupTimedOut(")
    assert callback_deadline_check < callback.index("latest_cmd_ = *msg")
    assert callback_deadline_check < callback.index("active_ = TRAJECTORY")

    trajectory = flight[flight.index("} else if (active_ == TRAJECTORY)"):]
    trajectory = trajectory[:trajectory.index("rclcpp_action::GoalResponse")]
    deadline_check = trajectory.index("trajectoryDeadlineExpired(")
    publish = trajectory.index("pub_uav_cmd_->publish(cmd)")
    assert deadline_check < publish


def test_waypoint_updates_fsm_asynchronously_and_cloud_stamp_uses_node_clock():
    fsm = read(EGO / "plan_manage/src/ego_replan_fsm.cpp")
    grid = read(EGO / "plan_env/src/grid_map.cpp")
    launch = read(LOCAL / "launch/local_planner.launch.py")

    waypoint_start = fsm.index("void EGOReplanFSM::planNextWaypoint")
    waypoint_end = fsm.index("void EGOReplanFSM::triggerCallback", waypoint_start)
    waypoint = fsm[waypoint_start:waypoint_end]
    assert "while (" not in waypoint
    assert "execFSMCallback()" not in waypoint
    assert "checkCollisionCallback()" not in waypoint
    assert "sleep_for" not in waypoint
    assert 'exec_state_ == WAIT_TARGET' in waypoint
    assert 'changeFSMExecState(GEN_NEW_TRAJ, "TRIG")' in waypoint
    assert 'exec_state_ == EXEC_TRAJ' in waypoint
    assert 'changeFSMExecState(REPLAN_TRAJ, "TRIG")' in waypoint
    assert "EMERGENCY_STOP" in waypoint
    assert "changeFSMExecState(EMERGENCY_STOP" not in waypoint

    assert "img->header.frame_id != mp_.frame_id_" in grid
    assert "node_->get_clock()->get_clock_type()" in grid
    assert "rclcpp::Time msg_stamp(img->header.stamp, clock_type)" in grid
    assert "age < -mp_.trusted_cloud_future_tolerance_" in grid
    assert "age > mp_.trusted_cloud_timeout_" in grid
    assert "grid_map/trusted_cloud_future_tolerance': 0.2" in launch


def test_waypoint_goal_admission_is_fail_closed_and_unit_covered():
    fsm = read(EGO / "plan_manage/src/ego_replan_fsm.cpp")
    header = read(EGO / "plan_manage/include/plan_manage/waypoint_admission.h")
    fsm_header = read(EGO / "plan_manage/include/plan_manage/ego_replan_fsm.h")
    cmake = read(EGO / "plan_manage/CMakeLists.txt")
    unit = read(EGO / "plan_manage/test/test_waypoint_admission.cpp")
    launch = read(LOCAL / "launch/local_planner.launch.py")

    waypoint = fsm[fsm.index("void EGOReplanFSM::waypointCallback"):
                   fsm.index("void EGOReplanFSM::odometryCallback")]
    assert "validOdomFrame" in waypoint
    assert "validStampFields" in waypoint
    assert "validTimestampWindow" in waypoint
    assert "nonDecreasingStamp" in waypoint
    assert "hasFreshOdom()" in waypoint
    assert waypoint.index("validOdomFrame") < waypoint.index("planNextWaypoint")
    assert waypoint.index("validTimestampWindow") < waypoint.index("planNextWaypoint")
    assert waypoint.index("hasFreshOdom()") < waypoint.index("planNextWaypoint")
    assert "last_waypoint_stamp_" in fsm_header
    assert "waypoint_stamp_valid_{false}" in fsm_header
    for helper in (
        "validOdomFrame", "validStampFields", "validTimestampWindow",
        "nonDecreasingStamp", "selectGoalAltitude"):
        assert helper in header
    for case in (
        "AcceptsOnlyOdomFrameSpellings", "RejectsZeroAndMalformedStampFields",
        "RejectsStaleFutureAndNonFiniteTimestampWindows",
        "RejectsRegressedWaypointStamp", "ExplicitAndLowAltitudeGoalsHaveSafeSemantics"):
        assert case in unit
    assert "ament_add_gtest(test_waypoint_admission" in cmake
    assert "fsm/waypoint_future_tolerance': 0.2" in launch


def test_odom_freshness_and_cloud_point_bound_have_behavior_coverage():
    plan_env = EGO / "plan_env"
    cmake = read(plan_env / "CMakeLists.txt")
    freshness_header = read(plan_env / "include/plan_env/odom_freshness.h")
    freshness_test = read(plan_env / "test/test_odom_freshness.cpp")
    assert "ament_add_gtest(test_odom_freshness" in cmake
    assert "evaluateOdomFreshness" in freshness_header
    assert "StoppedStreamBecomesStaleAndCannotKeepCloudAlive" in freshness_test
    assert "BackwardAndLargeForwardClockJumpsFailClosed" in freshness_test
    assert "NewValidSampleRecoversOnlyFromClearedTrustedState" in freshness_test
    grid_source = read(plan_env / "src/grid_map.cpp")
    from_ros = grid_source.index("pcl::fromROSMsg(*img, latest_cloud)")
    point_guard = grid_source.index("raw_point_count", grid_source.index("void GridMap::cloudCallback"))
    assert point_guard < from_ros


def test_fsm_planning_failures_cannot_overwrite_safety_states():
    fsm = read(EGO / "plan_manage/src/ego_replan_fsm.cpp")
    callback = fsm[fsm.index("void EGOReplanFSM::execFSMCallback"):]
    assert "if (exec_state_ == SEQUENTIAL_START)\n              enterEmergencyStop(\"FIRST_TRAJ_COLLISION\")" in callback
    assert re.search(
        r"if \(exec_state_ == GEN_NEW_TRAJ\)\s*(?:\{\s*)?"
        r"(?:[^}]|\}(?!\s*else))*changeFSMExecState\(GEN_NEW_TRAJ",
        callback,
    )
    assert re.search(
        r"if \(exec_state_ == REPLAN_TRAJ\)\s*\{?\s*"
        r"(?:[^}]|\}(?!\s*else))*changeFSMExecState\(REPLAN_TRAJ",
        callback,
    )
    # Successful planning must also avoid publishing a trajectory after a
    # concurrent safety transition changed the state.
    assert "if (exec_state_ == SEQUENTIAL_START)\n            {\n              changeFSMExecState(EXEC_TRAJ" in callback
    assert "if (exec_state_ == GEN_NEW_TRAJ)\n        {\n          changeFSMExecState(EXEC_TRAJ" in callback
    assert "if (exec_state_ == REPLAN_TRAJ)\n        {\n          changeFSMExecState(EXEC_TRAJ" in callback


def test_no_cloud_and_retry_loops_preserve_safety_states():
    fsm = read(EGO / "plan_manage/src/ego_replan_fsm.cpp")
    rebound = fsm[fsm.index("bool EGOReplanFSM::callReboundReplan"):]
    global_plan = fsm[fsm.index("bool EGOReplanFSM::planFromGlobalTraj"):]
    current_plan = fsm[fsm.index("bool EGOReplanFSM::planFromCurrentTraj"):]
    assert "if (exec_state_ == EMERGENCY_STOP)" in rebound
    assert "else if (exec_state_ == EXEC_TRAJ || exec_state_ == REPLAN_TRAJ)" in rebound
    assert "changeFSMExecState(WAIT_TARGET, \"NO_TRUSTED_CLOUD\")" in rebound
    assert "if (exec_state_ == WAIT_TARGET || exec_state_ == EMERGENCY_STOP)" in global_plan
    assert current_plan.count(
        "if (exec_state_ == WAIT_TARGET || exec_state_ == EMERGENCY_STOP)") >= 3


def test_ego_acceptance_does_not_cascade_e3_after_failed_e4():
    launch = read(ROOT / "test/ego_acceptance.launch.py")
    acceptance = read(ROOT / "test/ego_acceptance.py")
    assert "semantic = TimerAction(period=16.0" in launch
    assert "ego = TimerAction(period=20.0" in launch
    assert "if e4_ok and recovered:" in acceptance
    assert "E3 跳过：E4 未通过或机体尚未恢复 HOVER" in acceptance


def test_swarm_bspline_validation_precedes_all_buffer_and_eigen_mutations():
    validator = read(EGO / "plan_manage/include/plan_manage/swarm_bspline_validator.h")
    runtime_validator = read(
        EGO / "plan_manage/include/plan_manage/bspline_runtime_validator.h")
    fsm = read(EGO / "plan_manage/src/ego_replan_fsm.cpp")
    traj_server = read(EGO / "plan_manage/src/traj_server.cpp")
    cmake = read(EGO / "plan_manage/CMakeLists.txt")
    unit = read(EGO / "plan_manage/test/test_swarm_bspline_validator.cpp")
    assert "kMaxSwarmId = 64" in validator
    assert "kMaxControlPoints = 4096" in validator
    assert "kMaxControlPointAbs = 1000.0" in validator
    assert "kMaxDerivedVelocityAbs = 10000.0" in validator
    assert "kMaxDerivedAccelerationAbs = 100000.0" in validator
    assert "kConsumedBsplineOrder = 3" in validator
    assert "kMaxTrajectoryDuration = 300.0" in validator
    assert "validateBspline" in validator
    assert "validateMultiBsplines" in validator
    assert "validateCubicBspline" in validator
    assert "validPlanningHorizon" in validator
    assert "kMaxPlanningHorizon = 1000.0" in validator
    assert "msg.traj.size() != expected_trajectory_count" in validator
    assert "msg.traj[index].drone_id" in validator
    assert "kInternalKnotRepeat" in validator
    assert "kDerivativeDenominator" in validator
    assert "knot_count != expected_knot_count" in validator
    assert "std::isfinite(point.x)" in validator
    assert "duration <= 0.0" in validator

    broadcast_validation = fsm.index("validateCubicBspline(*msg)")
    broadcast_index = fsm.index("static_cast<size_t>(id_value)")
    broadcast_small_points = fsm.index("if (msg->pos_pts.size() < 3)", broadcast_validation)
    broadcast_distance = fsm.index("if ((swarm_start_pt - odom_pos_)", broadcast_validation)
    broadcast_commit = fsm.index("commitSwarmCandidate", broadcast_validation)
    assert broadcast_validation < broadcast_index
    assert broadcast_validation < broadcast_small_points < broadcast_distance < broadcast_commit
    broadcast_section = fsm[broadcast_validation:fsm.index(
        "void EGOReplanFSM::swarmTrajsCallback", broadcast_validation)]
    assert "swarm_trajs_buf_[id].drone_id" not in broadcast_section
    assert "validateCubicRuntimeTrajectory" in broadcast_section
    assert "canTransitionToReplan" in broadcast_section
    multi_validation = fsm.index("validateMultiBsplines(*msg)")
    multi_horizon = fsm.index("validPlanningHorizon(planning_horizen_)", multi_validation)
    multi_candidate = fsm.index("SwarmTrajData candidate_buffer", multi_validation)
    assert multi_horizon < multi_candidate
    multi_commit = fsm.index("swarm_trajs_buf_ = std::move(candidate_buffer)")
    assert multi_validation < multi_commit
    assert "validateCubicBspline(msg->traj[i])" in fsm
    assert "static_cast<Eigen::Index>(msg->traj[i].pos_pts.size())" in fsm
    assert "validateCubicRuntimeTrajectory" in runtime_validator
    assert "commitSwarmCandidate" in validator
    traj_validation = traj_server.index("validateCubicBspline(*msg)")
    traj_eigen = traj_server.index("static_cast<Eigen::Index>(msg->pos_pts.size())")
    traj_id_cast = traj_server.index("static_cast<uint32_t>(msg->traj_id)")
    assert traj_validation < traj_eigen < traj_id_cast
    assert "reject null B-spline message" in traj_server
    assert "candidate_velocity = candidate_position.getDerivative()" in traj_server
    assert "candidate_acceleration = candidate_velocity.getDerivative()" in traj_server
    assert "validateCubicRuntimeTrajectory" in traj_server
    assert "receive_traj_ = true" in traj_server
    assert "validateMultiBsplines(*msg)" in fsm
    assert "ament_add_gtest(test_swarm_bspline_validator" in cmake
    assert "RejectsNegativeAndHugeIdsBeforeIndexing" in unit
    assert "RejectsUnsupportedOrderAndOversizedVectors" in unit
    assert "ValidatesEveryMultiEntryAndYawFields" in unit
    assert "MultiRequiresIndexedTrajectoryIdentity" in unit
    assert "InvalidPlanningHorizonIsRejectedBeforeIngress" in unit


def test_g8_planner_keeps_the_08m_clearance_contract():
    launch = read(LOCAL / "launch/local_planner.launch.py")
    assert "'grid_map/obstacles_inflation': 0.80" in launch
    assert "'optimization/dist0': 0.80" in launch
    assert "Point-cloud surface + vehicle footprint/safety margin" in launch


def test_easyfly_map_x_has_margin_for_r20_boundary_pose_and_local_candidates():
    launch = read(LOCAL / "launch/local_planner.launch.py")
    helper = read(ROOT / "test/ego_local_goal_admission.py")
    grid = read(EGO / "plan_env/src/grid_map.cpp")
    assert "'grid_map/map_size_x': 80.0" in launch
    assert "'grid_map/map_size_y': 25.0" in launch
    assert "'grid_map/map_size_z': 5.0" in launch
    assert "'grid_map/local_update_range_x': 8.0" in launch
    assert "LOCAL_GOAL_LOCAL_UPDATE_HALF_M = 8.0" in helper
    assert "LOCAL_GOAL_UPDATE_RESERVE_M = 4.0" in helper
    assert "GridMap odom outside map; clearing trusted cloud" in grid

    # r20 E2 reached x≈25.19.  The old 50m map had x_max=25 and would reject
    # it; the current 80m map has x_max=40 and leaves the 4m candidate cap in
    # the valid interior.
    e2_x = 25.19
    old_half_x = 50.0 / 2.0
    new_half_x = 80.0 / 2.0
    candidate_cap = 4.0
    assert e2_x > old_half_x
    assert e2_x + candidate_cap < new_half_x
    assert e2_x - candidate_cap > -new_half_x


def test_g8_planner_floor_is_a_fail_closed_lower_boundary():
    launch = read(LOCAL / "launch/local_planner.launch.py")
    grid_header = read(EGO / "plan_env/include/plan_env/grid_map.h")
    grid_source = read(EGO / "plan_env/src/grid_map.cpp")
    optimizer = read(EGO / "bspline_opt/src/bspline_optimizer.cpp")

    # The semantic cloud is obstacle-surface input; it must not turn the map
    # origin into a permission to route below the physical flight floor.
    assert "'grid_map/ground_height': 0.5" in launch
    assert "规划最低飞行边界" in launch
    assert "不是 semantic_map 的地面剔除阈值" in launch
    assert "planning_floor=%.2fm" in grid_source
    assert "ground_height_ is the lower planning boundary" in grid_source

    # GridMap's out-of-map sentinel is deliberately truthy to the existing
    # collision callers, and the full B-spline validator must sample it.
    assert "Samples below it are outside the map and must fail closed" in grid_header
    assert "if (!isInMap(pos)) return -1;" in grid_header
    assert "fullTrajectorySampleTimes" in optimizer
    assert "if (collision_samples.empty())" in optimizer
    assert "for (const double t : collision_samples)" in optimizer
    assert "flag_occ = grid_map_->getInflateOccupancy" in optimizer


def test_g8_height_ceiling_is_scene_bound_and_hard_not_one_voxel_only():
    launch = read(LOCAL / "launch/local_planner.launch.py")
    acceptance_launch = read(ROOT / "test/ego_acceptance.launch.py")
    grid_header = read(EGO / "plan_env/include/plan_env/grid_map.h")
    grid_source = read(EGO / "plan_env/src/grid_map.cpp")
    ceiling_header = read(EGO / "plan_env/include/plan_env/virtual_ceiling.h")
    world = read(ROOT / "src/simulation/easyfly_gazebo_worlds/perception_demo.world")

    # The fixed-height bypass is a launch-level scenario policy, not a
    # relaxed clearance threshold: pillar_1 world top is 1.5 + 3/2 = 3.0m.
    # r21's observed ground/odom offset puts that same top near 2.36m in odom;
    # the G8 wrapper's 2.0m ceiling leaves hover≈1.5m usable but prevents a top pass.
    assert "declare_virtual_ceil = DeclareLaunchArgument(" in launch
    assert "'virtual_ceil_height', default_value='3.2'" in launch
    assert "'grid_map/virtual_ceil_height': virtual_ceil_height" in launch
    assert '{"virtual_ceil_height": "2.0"}' in acceptance_launch
    assert "<model name=\"pillar_1\">" in world
    assert "<pose>5 -2 1.5 0 0 0</pose>" in world
    assert "<size>1 1 3</size>" in world
    assert 1.5 < 2.0 < (3.0 - 0.64)

    # A single marked voxel at the ceiling is not enough: every optimizer
    # collision query must reject the continuous boundary and bad values.
    assert "virtualCeilingBlocks(pos(2), mp_.virtual_ceil_height_)" in grid_header
    assert "if (!std::isfinite(pos(0)) || !std::isfinite(pos(1))) return -1;" in grid_header
    assert 'declare_parameter<double>("grid_map/virtual_ceil_height",-1.0)' in grid_source
    assert "return z >= ceiling;" in ceiling_header
    assert "if (!std::isfinite(ceiling))" in ceiling_header


def test_grid_map_rejects_invalid_inflation_and_logs_effective_safety_parameters():
    grid = read(EGO / "plan_env/src/grid_map.cpp")
    helper = read(EGO / "plan_env/include/plan_env/inflation_safety.h")
    launch = read(LOCAL / "launch/local_planner.launch.py")
    assert "computeInflationKernel" in grid
    assert "!plan_env::computeInflationKernel" in grid
    assert "kMaxInflationMeters = 4.0" in helper
    assert "checkedKernelElements" in helper
    assert "kMaxInflationKernelElements" in helper
    assert "mp_.inflation_step_ = inflation_kernel.step" in grid
    assert "mp_.inflation_kernel_elements_ = inflation_kernel.kernel_elements" in grid
    assert "mp_.obstacles_inflation_ = 0.80" in grid
    assert "GridMap trusted cloud: frame=%s inflation=%.2fm" in grid
    assert "computeTrustedCloudVerticalStep" in helper
    assert "mp_.trusted_cloud_vertical_step_" in grid
    assert "const int inf_step_z = mp_.trusted_cloud_vertical_step_" in grid
    assert "grid_map/trusted_cloud_vertical_inflation': 0.40" in launch


def test_e1_clearance_keeps_threshold_and_reports_closest_pose():
    acceptance = read(ROOT / "test/ego_acceptance.py")
    e1_helper = read(ROOT / "test/ego_e1_admission.py")
    assert "def closest_sample_to_point" in acceptance
    assert "def max_sample_z_since" in acceptance
    assert "closest = self.closest_sample_to_point" in acceptance
    assert "min_d > 0.8" in acceptance
    assert "e1_pose_height_within_policy" in acceptance
    assert "E1_MAX_PLANNER_ALTITUDE_M" in e1_helper
    assert "E1_MAX_POSE_ALTITUDE_TOLERANCE_M" in e1_helper
    assert "first_new_trajectory_after" in acceptance
    assert "trajectory_t=%.2fs" in acceptance
    assert "trajectory_duration unavailable" in acceptance
    assert "progress ratio=NA" in acceptance
    assert "action_elapsed=%.2fs" in acceptance


def test_e2_clearance_reports_pose_obstacle_snapshot_without_lowering_gate():
    acceptance = read(ROOT / "test/ego_acceptance.py")
    admission = read(ROOT / "test/ego_e2_admission.py")
    e2 = acceptance[acceptance.index("    def e2_dynamic"):
                    acceptance.index("    def e4_takeover", acceptance.index("    def e2_dynamic"))]
    assert "min_clear_detail = None" in e2
    assert "_message_diag" in acceptance
    assert "arrival_mono" in acceptance
    assert "arrival_wall" in acceptance
    assert "current_node_ros" in e2
    assert "clock_mismatch" in e2
    assert "frame_id" in acceptance
    assert "min_clear > 0.8" in e2
    assert "admit_e2_pair" in e2
    assert "filter_counts" in e2
    assert "accepted_pairs" in e2
    assert "return follow_ok and clearance_ok and goal_ok" in e2
    assert "E2_MAX_MESSAGE_AGE_S = 1.0" in admission
    assert "E2_FUTURE_TOLERANCE_S = 0.2" in admission
    assert "E2_MAX_ARRIVAL_AGE_S = 1.5" in admission
    assert "state_disconnected" in admission
    assert "state_pose_invalid" in admission


def test_e2_goal_is_beyond_patrol_endpoint_not_inside_dynamic_work_area():
    acceptance = read(ROOT / "test/ego_acceptance.py")
    e2 = acceptance[acceptance.index("    def e2_dynamic"):
                    acceptance.index("    def e4_takeover", acceptance.index("    def e2_dynamic"))]
    assert "E2_PATROL_END_OFFSET_M = 17.0" in acceptance
    assert "E2_GOAL_CLEARANCE_BEYOND_PATROL_M = 3.0" in acceptance
    assert "px + E2_PATROL_END_OFFSET_M + E2_GOAL_CLEARANCE_BEYOND_PATROL_M" in e2
    assert "+ 13.0 + 4.0" not in e2
    # Keep the independent obstacle-clearance criterion unchanged.
    assert "min_clear > 0.8" in e2


def test_emergency_stop_entry_is_centralized_and_fail_closed():
    header = read(EGO / "plan_manage/include/plan_manage/ego_replan_fsm.h")
    source = read(EGO / "plan_manage/src/ego_replan_fsm.cpp")
    gate = read(EGO / "plan_manage/include/plan_manage/emergency_stop_gate.h")
    cmake = read(EGO / "plan_manage/CMakeLists.txt")
    assert "EmergencyStopGate emergency_stop_gate_" in header
    assert "void enterEmergencyStop(const char * reason)" in header
    assert source.count("changeFSMExecState(EMERGENCY_STOP") == 1
    assert "enterEmergencyStop(\"COLLISION_PLAN_FAILED\")" in source
    assert "enterEmergencyStop(\"ODOM_DEPTH_TIMEOUT\")" in source
    assert "enterEmergencyStop(\"FIRST_TRAJ_COLLISION\")" in source
    assert "emergency_stop_gate_.consume(true)" in source
    assert "emergency_stop_gate_.shouldReturnFromCollisionCallback" in source
    assert "emergency_stop_gate_.canCommitExecution" in source
    assert "emergency_stop_gate_.canTransitionToReplan" in source
    assert "if (exec_state_ != EXEC_TRAJ ||" in source
    assert "class EmergencyStopGate" in gate
    assert "ament_add_gtest(test_emergency_stop_gate" in cmake
    assert "test/test_emergency_stop_gate.cpp" in cmake
    assert "RemoteCollisionBroadcastCannotReplanWhileStopped" in read(
        EGO / "plan_manage/test/test_emergency_stop_gate.cpp")


def test_emergency_ack_is_one_shot_and_source_loss_is_fail_closed():
    gate = read(EGO / "plan_manage/include/plan_manage/emergency_stop_gate.h")
    fsm = read(EGO / "plan_manage/src/ego_replan_fsm.cpp")
    tests = read(EGO / "plan_manage/test/test_emergency_stop_gate.cpp")
    assert "TrajectoryAck is a one-shot" in gate
    assert "acknowledgedPublisherMatches" in gate
    assert "hasLiveTrajectoryAckSource" in fsm
    assert "ack_source_alive" in fsm
    assert "AckIsOneShotAndDoesNotExpireIntoRetry" in tests
    assert "LostAckPublisherForcesNewStopAttempt" in tests


def test_collision_safety_callback_does_not_reenter_emergency_planning():
    fsm = read(EGO / "plan_manage/src/ego_replan_fsm.cpp")
    callback = fsm[fsm.index("void EGOReplanFSM::checkCollisionCallback"):
                   fsm.index("bool EGOReplanFSM::callReboundReplan")]
    assert "exec_state_ == EMERGENCY_STOP" in callback
    assert "Let the FSM timer" in callback
    assert "perform the one bounded transition/replan" in callback
    assert "planFromCurrentTraj()" in callback


def test_g8_acceptance_requires_local_safe_goal_and_new_position_stream():
    acceptance = read(ROOT / "test/ego_acceptance.py")
    local_goal = read(ROOT / "test/ego_local_goal_admission.py")
    local_goal_unit = read(ROOT / "test/test_ego_local_goal_admission.py")
    assert "from quadrotor_msgs.msg import PositionCommand" in acceptance
    assert '"/position_cmd"' in acceptance
    assert '"/occupancy_grid"' in acceptance
    assert "from nav_msgs.msg import OccupancyGrid" in acceptance
    assert "admit_occupancy_grid_evidence" in acceptance
    assert "is_new_goal_trajectory" in acceptance
    assert "goal_is_active" in acceptance
    assert "follow_goal_status_diagnostic" in acceptance
    assert "wait_for_stable_hover_and_admission" in acceptance
    assert "position_cmd_history" in acceptance
    assert "def wait_for_new_trajectory" in acceptance
    assert "trajectory_id != baseline_id" in acceptance
    assert "def pick_local_safe_goal" in acceptance
    assert "select_local_safe_goal" in acceptance
    assert "observed_support_bounds" in local_goal
    assert "LOCAL_GOAL_LOCAL_UPDATE_HALF_M = 8.0" in local_goal
    assert "LOCAL_GOAL_UPDATE_RESERVE_M = 4.0" in local_goal
    assert "LOCAL_GOAL_MAX_TRAVEL_M" in local_goal
    assert "LOCAL_GOAL_MAX_PATH_SAMPLES = 4096" in local_goal
    assert "resolution/2 center-cell sample" in local_goal
    assert "occupancy_grid_path_is_safe" in local_goal
    assert "validate_occupancy_grid_metadata" in local_goal
    assert "path_clearance > clearance" in local_goal
    assert "strict 0.8m geometric clearance contract" in local_goal
    assert "clearance < LOCAL_GOAL_REQUIRED_CLEARANCE_M" in local_goal
    assert "required_samples" in local_goal
    assert "semantic_map" in local_goal
    assert "test_r19_does_not_admit_blind_x31_goal" in local_goal_unit
    assert "test_r19_candidate_has_minimum_motion" in local_goal_unit
    assert "test_grid_unknown_occupied_and_out_of_bounds_fail_closed" in local_goal_unit
    assert "test_r19_semantic_grid_inflation_fixture" in local_goal_unit
    assert "test_required_clearance_cannot_be_relaxed_below_0_8m" in local_goal_unit


def test_e3_recovery_wait_has_more_budget_without_relaxing_stability_gates():
    acceptance = read(ROOT / "test/ego_acceptance.py")
    start = acceptance.index("def wait_for_stable_hover_and_admission")
    end = acceptance.index("    def e1_static_avoid", start)
    wait = acceptance[start:end]
    assert "hold_s=0.5, timeout_s=30.0" in wait
    assert "speed <= 0.1" in wait
    assert "next_progress = start + 5.0" in wait
    assert "reason_counts = Counter()" in wait
    assert "last_speed=%.3fm/s" in wait
    assert "last_pose=%s" in wait
    assert "speed_limit=0.100m/s" in wait
    assert "while next_progress <= now" in wait
    grid_cb = acceptance[acceptance.index("    def _on_grid"):
                        acceptance.index("    def _on_fb", acceptance.index("    def _on_grid"))]
    assert "LOCAL_GOAL_MAX_GRID_CELLS" in grid_cb
    assert "len(raw_data) != cell_count" in grid_cb
    assert grid_cb.index("len(raw_data) != cell_count") < grid_cb.index(
        "data = tuple(int(value) for value in raw_data)")

    e4_start = acceptance.index("    def e4_takeover")
    e3_start = acceptance.index("    def e3_stream_cut", e4_start)
    e4 = acceptance[e4_start:e3_start]
    e3 = acceptance[e3_start:acceptance.index("\n\nRESULTS", e3_start)]
    assert "candidate = self.pick_local_safe_goal(p0)" in e4
    assert "p0[0] + 12.0" not in e4
    assert e4.index("wait_for_new_trajectory") < e4.index("call_async")
    assert "time.sleep(0.5)" in e4
    assert "E4 RTL 前 FollowTrajectory 仍 ACTIVE/ACCEPTED/EXECUTING" in e4
    assert "E4 RTL 事件后 action 状态" in e4
    assert e4.index("follow_goal_is_active") < e4.index("call_async")
    assert "self.cancel_goal(gh)" in e4
    assert "candidate = self.pick_local_safe_goal(p0)" in e3
    assert "p0[0] + 14.0" not in e3
    assert e3.index("wait_for_new_trajectory") < e3.index("pkill")
    # r27 审核后待办: 不再要求 kill 前 1s settle; 改为要求启动门(wait_for_new_
    # trajectory)与 pkill 之间无任何 sleep — 局部短轨迹 2-3s 即完成, settle
    # 窗口会把任务等成终态, 使流中断用例失去被测对象。
    pre_kill = e3[e3.index("wait_for_new_trajectory"):e3.index("pkill")]
    assert "time.sleep" not in pre_kill
    assert "E3 kill 前 FollowTrajectory 仍 ACTIVE/ACCEPTED/EXECUTING" in e3
    assert "E3 kill 事件后 action 状态" in e3
    assert e3.index("follow_goal_is_active") < e3.index("pkill")
    assert "self.cancel_goal(gh)" in e3
    assert "candidate = self.pick_local_safe_goal(p0, z=1.0)" not in e4 + e3
    assert "fg.target_x, fg.target_y, fg.target_z = candidate" in e4 + e3


def test_g8_acceptance_rejects_emergency_id_without_goal_progress():
    helper = read(ROOT / "test/trajectory_admission.py")
    behavior = read(ROOT / "test/test_ego_acceptance_e2.py")
    assert "goal_command_progress" in helper
    assert "trajectory_id" in helper
    assert "command_position" in helper
    assert "emergency_stop_new_id_without_goal_progress" in behavior
    assert "test_takeover_or_stream_cut_requires_goal_result_still_active" in behavior


def test_e3_e4_local_goal_reuses_e2_synchronized_evidence_gate():
    acceptance = read(ROOT / "test/ego_acceptance.py")
    helper_start = acceptance.index("    def _admitted_local_goal_snapshot")
    helper_end = acceptance.index("    def pick_local_safe_goal", helper_start)
    helper = acceptance[helper_start:helper_end]
    picker_start = helper_end
    picker_end = acceptance.index("    # ------------------------------------------------ 工具", picker_start)
    picker = acceptance[picker_start:picker_end]
    assert "admit_e2_pair" in helper
    assert "admit_occupancy_grid_evidence" in helper
    assert "last_state_diag" in helper and "last_obs_diag" in helper
    assert "last_grid_diag" in acceptance
    assert "time.monotonic()" in helper
    assert "_admitted_local_goal_snapshot" in picker
    assert "obstacles, occupancy_grid, reasons = self._admitted_local_goal_snapshot()" in picker
    assert "occupancy_grid=occupancy_grid" in picker
    assert "if obstacles is None" in picker


def test_e3_e4_pair_gate_rejects_separately_fresh_samples():
    admission = read(ROOT / "test/ego_e2_admission.py")
    fsm = read(EGO / "plan_manage/src/ego_replan_fsm.cpp")
    fsm_header = read(EGO / "plan_manage/include/plan_manage/ego_replan_fsm.h")
    gate = read(EGO / "plan_manage/include/plan_manage/emergency_stop_gate.h")
    assert "E2_MAX_PAIR_STAMP_S = 0.5" in admission
    assert "E2_MAX_PAIR_ARRIVAL_S = 0.5" in admission
    assert "pair_stamp_unsynchronized" in admission
    assert "pair_arrival_unsynchronized" in admission
    assert "trajectoryAckCallback" in fsm
    assert "traj_utils/msg/trajectory_ack.hpp" in fsm_header
    assert "trajectory_ack" in fsm
    assert "validTrajectoryAckSource" in fsm
    assert "trajectory_id" in fsm
    assert "downstream_acknowledged_" in gate
    assert "stable_start_time_" in gate


def test_odom_depth_timeout_requires_sensor_recovery_and_new_generation():
    fsm = read(EGO / "plan_manage/src/ego_replan_fsm.cpp")
    gate = read(EGO / "plan_manage/include/plan_manage/emergency_stop_gate.h")
    assert "odom_depth_timeout_latched_ = true" in fsm
    assert "canRecoverOdomDepthTimeout" in fsm
    assert "current_generation != stop_generation" in gate
    assert "enable_fail_safe_ = false" not in fsm


def test_ego_collision_checks_cover_the_complete_candidate_trajectory():
    optimizer = read(EGO / "bspline_opt/src/bspline_optimizer.cpp")
    sampling = read(EGO / "bspline_opt/include/bspline_opt/collision_sampling.h")
    fsm = read(EGO / "plan_manage/src/ego_replan_fsm.cpp")
    manager = read(EGO / "plan_manage/src/planner_manager.cpp")
    assert "fullTrajectorySampleTimes" in optimizer
    assert "boundedTrajectorySampleTimes" in sampling
    assert "max_speed_bound" in sampling
    assert "samples.push_back(end)" in sampling
    assert "getMaxVelocityBound" in optimizer
    assert "const double path_length" not in optimizer
    assert "tmp * 2 / 3" not in optimizer
    assert "1.0 / 3.0" not in optimizer
    assert "duration_ * 2 / 3" not in manager
    assert "fullTrajectorySampleTimes" in manager
    assert "relative_speed" in manager
    assert "t_2_3" not in fsm
    assert "boundedTrajectorySampleTimes" in fsm
    assert "kRuntimeLookaheadSeconds" in fsm
    assert "kRuntimeMaxIntervals" in fsm
    assert "for (const double t : collision_samples)" in fsm
    assert "if (collision_samples.empty())" in fsm
    assert "t_cur == duration" in fsm


def test_gen_new_traj_failure_is_rate_limited_and_bounded():
    header = read(EGO / "plan_manage/include/plan_manage/ego_replan_fsm.h")
    fsm = read(EGO / "plan_manage/src/ego_replan_fsm.cpp")
    gen_start = fsm.index("case GEN_NEW_TRAJ:")
    gen = fsm[gen_start:fsm.index("case REPLAN_TRAJ:", gen_start)]
    assert "std::chrono::steady_clock::time_point gen_retry_not_before_" in header
    assert "int gen_failure_count_{0}" in header
    assert "std::chrono::steady_clock::now() < gen_retry_not_before_" in gen
    assert "planFromGlobalTraj(1)" in gen
    # Keep the initial 250 ms retry, then cap GEN_NEW_TRAJ at 500 ms so an
    # 8-second startup grace is not consumed by 1 s/2 s backoff steps.
    assert "std::min(gen_failure_count_ - 1, 1)" in gen
    assert "std::chrono::milliseconds(250 * (1 << shift))" in gen
    assert "changeFSMExecState(GEN_NEW_TRAJ, \"FSM\")" in gen


def test_replan_failure_is_rate_limited_without_delaying_emergency_stop():
    header = read(EGO / "plan_manage/include/plan_manage/ego_replan_fsm.h")
    fsm = read(EGO / "plan_manage/src/ego_replan_fsm.cpp")
    replan_start = fsm.index("case REPLAN_TRAJ:")
    replan = fsm[replan_start:fsm.index("case EXEC_TRAJ:", replan_start)]
    assert "std::chrono::steady_clock::time_point replan_retry_not_before_" in header
    assert "int replan_failure_count_{0}" in header
    assert "std::chrono::steady_clock::now() < replan_retry_not_before_" in replan
    assert "planFromCurrentTraj(1)" in replan
    # REPLAN_TRAJ retains its independent 2 s ceiling.
    assert "std::min(replan_failure_count_ - 1, 3)" in replan
    assert "std::chrono::milliseconds(250 * (1 << shift))" in replan
    assert "if (exec_state_ == REPLAN_TRAJ)" in replan
    assert "new_state == REPLAN_TRAJ && exec_state_ != REPLAN_TRAJ" in fsm
    # A failure that entered EMERGENCY_STOP must not acquire a retry budget or
    # overwrite the safety state on the way out of planFromCurrentTraj().
    failure = replan[replan.index("else"):]
    assert failure.index("if (exec_state_ == REPLAN_TRAJ)") < failure.index(
        "replan_retry_not_before_")
    collision = fsm[fsm.index("void EGOReplanFSM::checkCollisionCallback"):
                    fsm.index("bool EGOReplanFSM::callReboundReplan")]
    assert "REPLAN_TRAJ is already owned by the FSM timer" in collision
    assert "REPLAN_COLLISION_IMMINENT" in collision
    assert collision.index("if (exec_state_ == REPLAN_TRAJ)") < collision.index(
        "const bool planned = planFromCurrentTraj()")


def test_collision_margin_is_checked_before_and_after_replan_on_same_time_origin():
    fsm = read(EGO / "plan_manage/src/ego_replan_fsm.cpp")
    safety = read(EGO / "plan_manage/include/plan_manage/collision_safety.h")
    unit = read(EGO / "plan_manage/test/test_waypoint_admission.cpp")
    init = fsm[fsm.index("void EGOReplanFSM::init"):
               fsm.index("void EGOReplanFSM::readGivenWps")]
    collision = fsm[fsm.index("void EGOReplanFSM::checkCollisionCallback"):
                    fsm.index("bool EGOReplanFSM::callReboundReplan")]

    assert "sanitizeEmergencyTime" in init
    assert "emergency_time_ = collision_safety::sanitizeEmergencyTime" in init
    assert "emergencyWindowImminent" in safety
    pre = collision.index("const double collision_t_cur")
    plan = collision.index("const bool planned = planFromCurrentTraj()")
    post = collision.index("const double post_plan_t_cur")
    commit = collision.index('changeFSMExecState(EXEC_TRAJ, "SAFETY")')
    assert pre < plan < post < commit
    assert "const rclcpp::Time collision_start_time = info->start_time_" in collision
    assert "const double collision_duration = info->duration_" in collision
    assert "(node_->get_clock()->now() - collision_start_time).seconds()" in collision
    assert "current < 0.0" in collision
    assert "EmergencyTimeAndBoundaryAreFailClosed" in unit


def test_invalid_collision_trajectory_time_enters_central_emergency_stop():
    fsm = read(EGO / "plan_manage/src/ego_replan_fsm.cpp")
    safety = read(EGO / "plan_manage/include/plan_manage/collision_safety.h")
    unit = read(EGO / "plan_manage/test/test_waypoint_admission.cpp")
    collision = fsm[fsm.index("void EGOReplanFSM::checkCollisionCallback"):
                    fsm.index("bool EGOReplanFSM::callReboundReplan")]
    duration_guard = collision.index(
        "if (!collision_safety::validTrajectoryDuration(info->duration_))")
    duration_stop = collision.index(
        'enterEmergencyStop("INVALID_TRAJECTORY_TIME")', duration_guard)
    normal_path = collision.index("t_cur = std::min", duration_guard)
    assert "validTrajectoryDuration" in safety
    assert duration_guard < duration_stop < normal_path
    assert "enterEmergencyStop(\"INVALID_TRAJECTORY_CLOCK\")" in collision
    assert "InvalidTrajectoryDurationIsRejected" in unit


def test_e1_goal_uses_fresh_geometry_bypass_and_hover_altitude():
    acceptance = read(ROOT / "test/ego_acceptance.py")
    helper = read(ROOT / "test/ego_e1_admission.py")
    fsm = read(EGO / "plan_manage/src/ego_replan_fsm.cpp")
    unit = read(ROOT / "test/test_ego_acceptance_e1.py")
    assert "select_e1_opposite_goal" in acceptance
    assert "_admitted_obstacle_snapshot" in acceptance
    assert "admitted_hover_altitude" in acceptance
    assert "E1_REQUIRED_CLEARANCE_M = 0.8" in helper
    assert "E1_MIN_OPPOSITE_OFFSET_M = 4.0" in helper
    assert "_point_segment_distance" in helper
    assert "terminal_clearance > clearance" in helper
    assert "goal_z = admitted_hover_altitude" in acceptance
    assert "fg.target_x, fg.target_y, fg.target_z = gx, gy, goal_z" in acceptance
    assert "self.publish_ego_goal(gx, gy, goal_z)" in acceptance
    assert "1.0)   # 立柱对侧 3m" not in acceptance
    # The planner must consume a valid requested z; otherwise changing E1/E2
    # to hover altitude would be silently discarded by the old 1.0m constant.
    waypoint = fsm[fsm.index("void EGOReplanFSM::waypointCallback"):
                   fsm.index("void EGOReplanFSM::odometryCallback")]
    assert "double goal_z = msg->pose.position.z" in waypoint
    assert "odom_pos_.z()" in waypoint
    assert "Eigen::Vector3d end_wp(msg->pose.position.x, msg->pose.position.y, goal_z)" in waypoint
    assert "test_goal_is_derived_beyond_observed_anchor" in unit


def test_ground_tracker_freezes_trusted_model_while_armed():
    header = read(SEMANTIC / "include/easyfly_semantic_map/ground_plane_tracker.hpp")
    source = read(SEMANTIC / "src/semantic_map_node.cpp")
    unit = read(SEMANTIC / "test/test_ground_plane_tracker.cpp")
    assert "kFrozen" in header
    assert "model_valid_ && (!vehicleStateFresh(vehicle) || vehicle.armed)" in header
    assert "bool vehicleStateFresh" in header
    assert "return GroundPlaneUpdate::kFrozen" in header
    assert "plane_update == GroundPlaneUpdate::kFrozen" in source
    assert "UAV 状态无效/过期" in source
    assert "FreezesTrustedModelWhileArmed" in unit
    assert "FreezesTrustedModelWhenDisconnected" in unit
    assert "FreezesTrustedModelWhenPoseIsInvalid" in unit
    assert "FreezesTrustedModelWhenStateIsStale" in unit
    assert "FreshDisarmedStateRecoversAfterStaleFreeze" in unit
    assert "DisarmedStateCanUpdateAfterArmedFreeze" in unit


def test_nonground_stream_uses_current_voxelized_cloud_and_prediction_only():
    source = read(SEMANTIC / "src/semantic_map_node.cpp")
    config = read(SEMANTIC / "config/semantic_map.yaml")
    assert "pcl::VoxelGrid<pcl::PointXYZI>" in source
    assert "current_nonground" in source
    assert "merged_nonground" in source
    assert "nonground_voxel_size" in source
    assert "nonground_voxel_size: 0.10" in config
    assert "pcl::toROSMsg(*obs, nonground_msg)" not in source
    assert "pcl::toROSMsg(*merged_nonground, nonground_msg)" in source
    assert "acc_buf_" not in source
    assert "dynamic_history_" not in source
    assert "dynamic_ghost_ttl" not in source
    assert "dynamic_tracker_.predict(" in source
    assert "current_predicted_points" in source
    assert "nonground_msg.header.frame_id = params_.world_frame" in source
    assert "nonground_msg.header.stamp = msg->header.stamp" in source


def test_semantic_map_invalidates_all_consumers_on_input_failure_and_recovers():
    source = read(SEMANTIC / "src/semantic_map_node.cpp")
    config = read(SEMANTIC / "config/semantic_map.yaml")
    assert "input_watchdog_timer_" in source
    assert "checkInputWatchdog" in source
    assert "last_input_ros_ns_" in source
    assert 'invalidateMap("收到空点云，清除 semantic_map")' in source
    assert 'invalidateMap("输入点云 TF 不可用，清除 semantic_map")' in source
    assert 'invalidateMap("车辆位姿 TF 不可用，清除 semantic_map")' in source
    assert 'invalidateMap("UAV 状态未连接/位姿无效/过期，清除 semantic_map")' in source
    assert 'invalidateMap("TF 位置跳变，清除 semantic_map")' in source
    assert 'invalidateMap("pointcloud 输入超时，清除 semantic_map")' in source
    assert "publishEmptyNonground" in source
    assert "empty.header.frame_id = params_.world_frame" in source
    assert "publishEmptyNonground(this->now())" in source
    assert "invalid_published_" in source
    assert "map_ready_ = false" in source
    assert "input_timeout: 1.0" in config


def test_valid_empty_window_keeps_nonground_and_invalid_odom_clears_trusted_layer():
    semantic = read(SEMANTIC / "src/semantic_map_node.cpp")
    grid = read(EGO / "plan_env/src/grid_map.cpp")
    persistence = read(EGO / "plan_env/include/plan_env/trusted_cloud_persistence.h")

    ready_start = semantic.index("void publishReadyEmptyMap")
    ready_end = semantic.index("void invalidateMap", ready_start)
    ready_empty = semantic[ready_start:ready_end]
    assert "nonground != nullptr && !nonground->empty()" in ready_empty
    assert "publishEmptyNonground(stamp)" in ready_empty
    assert "grid_persist_.clear()" not in ready_empty

    assert "void GridMap::clearTrustedCloudState()" in grid
    assert "plan_env::clearTrustedCloudStorage" in grid
    assert "odom->header.frame_id != mp_.frame_id_" in grid
    assert "if (!md_.has_odom_)" in grid
    assert "clearTrustedCloudState();" in grid
    assert "std::isfinite(position.x)" in grid
    assert "std::isfinite(age)" in grid
    assert "age[i] + 1U < limit" in persistence


def test_semantic_map_has_explicit_current_cloud_resource_bounds():
    source = read(SEMANTIC / "src/semantic_map_node.cpp")
    config = read(SEMANTIC / "config/semantic_map.yaml")
    assert "kHardMaxInputPoints = 500000" in source
    assert "kHardMaxNongroundPoints = 1000000" in source
    assert "raw_point_count" in source
    assert "max_input_points" in source
    assert "max_nonground_points" in source
    assert "pcl::VoxelGrid<pcl::PointXYZI> voxel" in source
    assert "current_nonground" in source
    assert "当前非地面点云超过资源上限" in source
    assert "max_input_points: 200000" in config
    assert "max_nonground_points: 200000" in config
    assert "kDownstreamTrustedCloudPointLimit = 200000" in source
    assert "boundedCompletePredictionPointCount" in source
    assert "accumulate_frames" not in config
    assert "dynamic_ghost_ttl" not in config


def test_semantic_map_separates_clock_sampling_from_input_arrival():
    source = read(SEMANTIC / "src/semantic_map_node.cpp")
    config = read(SEMANTIC / "config/semantic_map.yaml")
    assert "last_clock_sample_ns_" in source
    assert "clock_sample_valid_" in source
    assert "sampleRosClock" in source
    assert "ClockSampleStatus::kJumped" in source
    assert "delta_ns < 0" in source
    assert "delta_ns > jump_limit_ns" in source
    assert "now_ns <= 0" in source
    assert "input_seen_ = false" in source
    assert "clock_jump_forward_limit" in source
    assert "clock_jump_forward_limit: 10.0" in config

    cloud_start = source.index("void onCloud")
    cloud = source[cloud_start:source.index("// ---- 2D 占据栅格", cloud_start)]
    assert cloud.index("sampleRosClock(now_ns)") < cloud.index("noteInputArrival(now_ns)")
    assert "clock_status != ClockSampleStatus::kUsable" in cloud


def test_cloud_stamp_is_validated_before_processing_or_tracker_mutation():
    source = read(SEMANTIC / "src/semantic_map_node.cpp")
    config = read(SEMANTIC / "config/semantic_map.yaml")
    assert "bool validateCloudStamp" in source
    assert "cloud_stamp_timeout" in source
    assert "cloud_stamp_future_tolerance" in source
    assert "rclcpp::Time(msg.header.stamp, get_clock()->get_clock_type())" in source
    assert "age_s <= params_.cloud_stamp_timeout" in source
    assert "age_s >= -params_.cloud_stamp_future_tolerance" in source
    assert "cloud_stamp_timeout: 1.0" in config
    assert "cloud_stamp_future_tolerance: 0.2" in config

    cloud_start = source.index("void onCloud")
    cloud = source[cloud_start:source.index("// ---- 2D 占据栅格", cloud_start)]
    stamp_index = cloud.index("validateCloudStamp(*msg, now_ns, stamp)")
    assert stamp_index < cloud.index("pcl::fromROSMsg")
    assert stamp_index < cloud.index("lookupTf")
    assert stamp_index < cloud.index("ground_tracker_.update")
    assert stamp_index < cloud.index("last_obstacle_stamp_ns_ = stamp_ns")
    assert "点云时间戳为零/过旧/未来或不可转换" in cloud
    assert "点云时间戳重复/回退，清除动态跟踪与 semantic_map" in cloud
    assert "void resetObstacleTracking()" in source


def test_complete_empty_window_keeps_trusted_cloud_and_can_recover():
    source = read(SEMANTIC / "src/semantic_map_node.cpp")
    assert "void publishReadyEmptyMap" in source
    assert "map_ready_ = true" in source
    assert "publishMarkers(header, {})" in source
    assert "publishEmptyNonground(stamp)" in source
    ready_start = source.index("void publishReadyEmptyMap")
    ready_end = source.index("void invalidateMap", ready_start)
    ready_empty = source[ready_start:ready_end]
    assert "grid_persist_.clear()" not in ready_empty
    assert "nonground != nullptr && !nonground->empty()" in ready_empty
    assert "publishReadyEmptyMap(empty_header, merged_nonground.get())" in source
    assert "publishReadyEmptyMap(arr.header, merged_nonground.get())" in source

    cloud_start = source.index("void onCloud")
    cloud = source[cloud_start:source.index("// ---- 2D 占据栅格", cloud_start)]
    empty_window = cloud.index("if (merged->size() <")
    assert empty_window < cloud.index("pcl::EuclideanClusterExtraction")
    assert cloud.index("publishReadyEmptyMap(arr.header, merged_nonground.get())") > cloud.index(
        "if (arr.obstacles.empty())")


def test_nonground_voxel_size_is_safe_after_float_conversion():
    source = read(SEMANTIC / "src/semantic_map_node.cpp")
    config = read(SEMANTIC / "config/semantic_map.yaml")
    assert "kMinimumNongroundVoxelSize = 0.02" in source
    assert "configured_voxel_size" in source
    assert "std::isfinite(configured_voxel_size)" in source
    assert "configured_voxel_size <= 0.0f" in source
    assert "nonground_voxel_size < kMinimumNongroundVoxelSize" in source
    assert "nonground_voxel_size: 0.10" in config


def test_g8_skips_e2_when_e1_fails_but_continues_recovery_and_e4():
    acceptance = read(ROOT / "test/ego_acceptance.py")
    assert "return follow_ok and clearance_ok and goal_ok" in acceptance
    assert "e1_ok = run_case(node, \"E1 静态绕障\", node.e1_static_avoid)" in acceptance
    assert "if e1_ok:" in acceptance
    assert "E2 跳过（依赖 E1 失败）" in acceptance
    assert "E1 后恢复 HOVER/重新起飞" in acceptance
    assert acceptance.index("e1_ok = run_case") < acceptance.index(
        "e4_ok = run_case")


def test_dedicated_traj_server_ack_is_wired_in_every_production_entry():
    """Keep old XML and current Python launch paths on one ACK contract.

    This is intentionally a source/launch contract test: a live graph test is
    provided separately and is opt-in because starting traj_server in a normal
    unit-test process would leave a ROS daemon and DDS endpoints behind.
    """
    msg = read(EGO / "traj_utils/msg/TrajectoryAck.msg")
    fsm = read(EGO / "plan_manage/src/ego_replan_fsm.cpp")
    traj_server = read(EGO / "plan_manage/src/traj_server.cpp")
    gate = read(EGO / "plan_manage/include/plan_manage/emergency_stop_gate.h")
    fsm_header = read(EGO / "plan_manage/include/plan_manage/ego_replan_fsm.h")
    traj_utils_package = read(EGO / "traj_utils/package.xml")

    assert "uint32 trajectory_id" in msg
    assert "uint64 activation_sequence" in msg
    assert "STATUS_ACCEPTED=1" in msg
    assert "get_publishers_info_by_topic" in fsm
    assert "publisher_gid" in fsm
    assert "endpointFqnMatches" in fsm
    assert "traj_server_node_fqn" in fsm
    assert "msg->activation_sequence" in fsm
    assert "publisher_key" in fsm
    assert "validTrajectoryAckSource" in fsm
    assert "traj_utils/msg/trajectory_ack.hpp" in fsm_header
    assert "positionCommandCallback" not in fsm
    assert "trajectory_ack_pub->publish" in traj_server
    assert traj_server.index("receive_traj_ = true") < traj_server.index(
        "trajectory_ack_pub->publish")
    assert "validTrajectoryAckSource" in gate
    assert "DDS Security" in gate
    assert "publisher_sequences_" in gate
    assert "attempt_publisher_key_" in gate
    assert "traj_server_node_fqn_" in fsm_header
    assert "<depend>builtin_interfaces</depend>" in traj_utils_package
    assert "<depend>geometry_msgs</depend>" in traj_utils_package

    launch_paths = (
        LOCAL / "launch/local_planner.launch.py",
        EGO / "plan_manage/launch/advanced_param.launch.py",
        EGO / "plan_manage/launch/advanced_param.xml",
        EGO / "plan_manage/launch/single_run_in_sim.launch.py",
        EGO / "plan_manage/launch/single_run_in_sim.launch",
        EGO / "plan_manage/launch/run_in_sim.launch",
        EGO / "plan_manage/launch/single_run_real.launch.py",
    )
    for path in launch_paths:
        text = read(path)
        assert "trajectory_ack" in text, path
        if path.suffix == ".xml":
            assert "fsm/traj_server_ack_topic" in text, path
            if "type=\"traj_server\"" in text:
                assert "remap from=\"trajectory_ack\"" in text, path
                assert "traj_server/ack_topic" in text, path
                assert "traj_server/source_node_name" in text, path
            else:
                assert "remap from=\"~trajectory_ack\"" in text, path


def test_live_ack_graph_harness_covers_valid_rejected_and_source_gate_cases():
    harness = ROOT / "test/test_traj_server_ack_graph.py"
    text = read(harness)
    assert "E4_RUN_ROS_GRAPH" in text
    assert "valid B-spline" in text
    assert "rejected B-spline" in text
    assert "fake/multi-publisher" in text


# ---------------------------------------------------------------------------
# r27 审核后待办② / r29 审核收尾待办①: E3 kill 门的行为级回归。
# 隔离: monkeypatch 作用域内替换 module.time.sleep / module.subprocess.run,
# 测试结束自动恢复, 不污染同进程其他测试。
# 覆盖边界: 使用假 goal handle + 缓存的假 result future, 保留真实
# follow_goal_is_active(), 覆盖 未完成 future / SUCCEEDED / ABORTED 三态 —
# 即真实 future 状态读取链路 (非仅打桩布尔)。
# ---------------------------------------------------------------------------

import importlib.util
import types

import pytest
from action_msgs.msg import GoalStatus


@pytest.fixture
def module():
    """加载 ego_acceptance 模块 (不执行 main; 需 ROS 环境)。"""
    spec = importlib.util.spec_from_file_location(
        "ego_acceptance_under_test", ROOT / "test/ego_acceptance.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeFuture:
    def __init__(self, done, wrapped=None):
        self._done = done
        self._wrapped = wrapped

    def done(self):
        return self._done

    def result(self):
        return self._wrapped


class _FakeGoalHandle:
    def __init__(self, future):
        self.accepted = True
        self._future = future

    def get_result_async(self):
        return self._future


def _make_e3_harness(module, monkeypatch, future, kill_calls):
    """构造不经过 rclpy 初始化的 EgoAcceptance 实例并打桩。

    future: 假 result future (未完成=active; 完成+status=终态)。
    follow_goal_is_active 保持真实实现 — 经 _result_future 缓存读取假 future。
    """
    import types

    harness = module.EgoAcceptance.__new__(module.EgoAcceptance)
    harness.ac_follow = object()
    harness._result_futures = {}
    harness.ensure_hover = lambda: True
    harness.wait_for_stable_hover_and_admission = lambda: True
    state = types.SimpleNamespace(
        position_x=0.0, position_y=0.0, position_z=1.5,
        armed=True, flight_mode=3)
    harness.snap = lambda: state
    harness.pick_local_safe_goal = lambda p0, z=None: (3.0, 0.0, 1.5)
    harness.send_goal = lambda client, goal, **kw: _FakeGoalHandle(future)
    harness.position_cmd_snapshot = lambda: (0, 0)
    harness.publish_ego_goal = lambda *a, **k: None
    harness.wait_for_new_trajectory = lambda *a, **k: 46
    harness.cancel_goal = lambda goal_handle: None

    def fake_wait_result(goal_handle, timeout):
        res = types.SimpleNamespace(message="stream_lost")
        return GoalStatus.STATUS_ABORTED, res
    harness.wait_result = fake_wait_result

    monkeypatch.setattr(module.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        module.subprocess, "run",
        lambda cmd, **kw: kill_calls.append(cmd))
    return harness


def test_e3_does_not_kill_or_pass_when_goal_already_succeeded(module, monkeypatch):
    kill_calls = []
    wrapped = types.SimpleNamespace(status=GoalStatus.STATUS_SUCCEEDED)
    harness = _make_e3_harness(
        module, monkeypatch, _FakeFuture(True, wrapped), kill_calls)
    before = len(module.RESULTS)
    assert harness.e3_stream_cut() is False
    assert kill_calls == [], "action 已 SUCCEEDED 时不得注入 kill 故障"
    after = module.RESULTS[before:]
    assert not any(ok and "断流" in name for name, ok in after), (
        "终态路径不得把旧结果记成断流通过")
    assert any((not ok) and "kill 前" in name for name, ok in after), (
        "终态路径必须以 kill 前 active 门失败")


def test_e3_does_not_kill_or_pass_when_goal_already_aborted_stream_lost(
        module, monkeypatch):
    kill_calls = []
    wrapped = types.SimpleNamespace(status=GoalStatus.STATUS_ABORTED)
    harness = _make_e3_harness(
        module, monkeypatch, _FakeFuture(True, wrapped), kill_calls)
    before = len(module.RESULTS)
    assert harness.e3_stream_cut() is False
    assert kill_calls == [], (
        "action 已 ABORTED(stream_lost) 时不得注入 kill — 否则旧终态会被"
        "归因于 kill 而假通过")
    after = module.RESULTS[before:]
    assert not any(ok and "断流" in name for name, ok in after), (
        "终态路径不得把旧 stream_lost 记成断流通过")
    assert any((not ok) and "kill 前" in name for name, ok in after)


def test_e3_kills_once_only_when_goal_still_active(module, monkeypatch):
    kill_calls = []
    harness = _make_e3_harness(
        module, monkeypatch, _FakeFuture(False), kill_calls)
    before = len(module.RESULTS)
    assert harness.e3_stream_cut() is True
    assert len(kill_calls) == 1 and "pkill" in kill_calls[0][0]
    after = module.RESULTS[before:]
    assert any(ok and "kill 前" in name for name, ok in after), (
        "未完成 future (active) 必须通过 kill 前门")

