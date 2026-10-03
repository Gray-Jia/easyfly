"""ROS-free geometry tests for the G8 E1 static bypass admission."""

try:
    from ego_e1_admission import (
        E1_MAX_POSE_ALTITUDE_TOLERANCE_M,
        E1_MAX_PLANNER_ALTITUDE_M,
        E1_MIN_OPPOSITE_OFFSET_M,
        E1_REQUIRED_CLEARANCE_M,
        admitted_hover_altitude,
        e1_pose_height_within_policy,
        select_e1_opposite_goal,
        xy_obstacle_clearance,
    )
except ModuleNotFoundError:
    from test.ego_e1_admission import (
        E1_MAX_POSE_ALTITUDE_TOLERANCE_M,
        E1_MAX_PLANNER_ALTITUDE_M,
        E1_MIN_OPPOSITE_OFFSET_M,
        E1_REQUIRED_CLEARANCE_M,
        admitted_hover_altitude,
        e1_pose_height_within_policy,
        select_e1_opposite_goal,
        xy_obstacle_clearance,
    )


def test_goal_is_derived_beyond_observed_anchor_and_keeps_bypass_geometry():
    origin = (0.2, -0.1)
    anchor = (5.1, -1.9)
    obstacles = (
        # The selected pillar is deliberately not a world-coordinate fixture:
        # the helper only sees the synchronized geometry supplied by caller.
        (5.1, -1.9, 1.0, 1.2),
        (12.0, 4.0, 1.0, 1.0),
    )
    result = select_e1_opposite_goal(origin, anchor, obstacles)
    assert result is not None
    gx, gy, terminal_clearance, base_offset = result
    ux = (anchor[0] - origin[0])
    uy = (anchor[1] - origin[1])
    assert (gx - anchor[0]) * ux + (gy - anchor[1]) * uy > 0.0
    # Collinearity means the direct route reaches the pillar plane and must be
    # bypassed; a goal merely offset to a free side would not satisfy E1.
    cross = ((gx - origin[0]) * (anchor[1] - origin[1]) -
             (gy - origin[1]) * (anchor[0] - origin[0]))
    assert abs(cross) < 1.0e-6
    assert base_offset >= E1_MIN_OPPOSITE_OFFSET_M
    assert terminal_clearance > E1_REQUIRED_CLEARANCE_M
    assert xy_obstacle_clearance(gx, gy, obstacles[0]) > E1_REQUIRED_CLEARANCE_M


def test_goal_rejects_missing_anchor_or_occupied_terminal_candidates():
    origin = (0.0, 0.0)
    anchor = (5.0, 0.0)
    assert select_e1_opposite_goal(
        origin, anchor, ((8.0, 8.0, 1.0, 1.0),)) is None
    # Block every bounded terminal candidate on the same ray.  The helper
    # must fail closed instead of lowering the 0.8m gate or moving sideways.
    assert select_e1_opposite_goal(
        origin, anchor,
        ((5.0, 0.0, 1.0, 1.0), (9.0, 0.0, 20.0, 20.0))) is None


def test_hover_altitude_is_finite_and_tied_to_takeoff_height():
    assert admitted_hover_altitude(1.5) == 1.5
    assert admitted_hover_altitude(1.5 + 0.35 - 1.0e-9) is not None
    assert admitted_hover_altitude(1.5 + 0.351) is None
    assert admitted_hover_altitude(float("nan")) is None


def test_e1_pose_height_stays_below_pillar_top_policy():
    assert E1_MAX_PLANNER_ALTITUDE_M == 2.0
    assert E1_MAX_POSE_ALTITUDE_TOLERANCE_M == 0.15
    assert e1_pose_height_within_policy(2.0)
    assert e1_pose_height_within_policy(
        E1_MAX_PLANNER_ALTITUDE_M + E1_MAX_POSE_ALTITUDE_TOLERANCE_M)
    assert not e1_pose_height_within_policy(
        E1_MAX_PLANNER_ALTITUDE_M + E1_MAX_POSE_ALTITUDE_TOLERANCE_M + 1.0e-6)
    assert not e1_pose_height_within_policy(3.02)
    assert not e1_pose_height_within_policy(float("nan"))
